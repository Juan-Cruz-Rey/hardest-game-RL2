"""Motor de simulacion (sin render).

`GameEngine` mantiene el estado del nivel y avanza la fisica un step a la vez.
NO depende de pygame: se puede correr "headless" para RL. El render vive en
`render.py` y solo lee el estado de esta clase.

Replica la mecanica del original (The World's Hardest Game, AS2):
- Movimiento del cuadrado rojo a `speed` px/step (ejes independientes).
- Colision con paredes: se cancela el desplazamiento por eje (como el hitTest
  pixel-perfect del original que deshace el paso eje por eje).
- Restriccion al `play_area`: el jugador no puede salir de la union de rects jugables.
- Muerte al tocar una bola -> respawn en el ultimo checkpoint.
- Tocar la meta (con las monedas requeridas) -> victoria.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

from level import Ball, Level, Rect


# Acciones discretas: combinaciones de las 4 direcciones (incluye diagonales y nada).
# El indice es estable para usarlo como espacio de accion de RL.
ACTIONS: List[Tuple[int, int]] = [
    (0, 0),    # 0 quieto
    (1, 0),    # 1 derecha
    (-1, 0),   # 2 izquierda
    (0, -1),   # 3 arriba
    (0, 1),    # 4 abajo
    (1, -1),   # 5 der-arriba
    (1, 1),    # 6 der-abajo
    (-1, -1),  # 7 izq-arriba
    (-1, 1),   # 8 izq-abajo
]


@dataclass
class BallState:
    """Estado mutable de una bola en simulacion."""
    x: float
    y: float
    radius: float
    _t: float  # tiempo interno (steps) para evaluar el patron


class GameEngine:
    """Simulacion pura de un nivel. Avanza con `step(action)`.

    Estado expuesto (solo lectura para el render): player_x/y, balls, won, dead,
    coins_collected, deaths, steps.
    """

    def __init__(self, level: Level):
        self.level = level
        self.reset()

    # ------------------------------------------------------------------ ciclo
    # Animacion de muerte del original: alpha baja 4/frame de 100 a 0 antes de
    # respawnear. Son 100/4 = 25 frames en los que el jugador no puede moverse.
    DEATH_FADE_FRAMES = 25

    def reset(self) -> None:
        self.player_x, self.player_y = self.level.spawn
        self.current_respawn = self._spawn_point()
        self.coins_collected = 0
        self._coin_taken = [False] * len(self.level.coins)
        self.deaths = 0
        self.steps = 0
        self.won = False
        self.dead = False          # True el step exacto del impacto (transitorio)
        self.move_ready = True     # replica _root.moveReady
        self.alpha = 100           # replica _alpha del jugador (100 = vivo)
        self.balls: List[BallState] = [self._init_ball(b) for b in self.level.balls]

    def step(self, action) -> None:
        """Avanza un step de fisica replicando el orden del enterFrame original.

        `action` = indice en ACTIONS o tupla (dx,dy).
        """
        if self.won:
            return
        self.dead = False
        dx, dy = self._decode_action(action)

        # 1) Las bolas se mueven siempre (su tween corre independiente del jugador).
        self._update_balls()

        # 2) Si esta en animacion de muerte (moveReady=false): bajar alpha y, al
        #    llegar a 0, respawnear. El jugador no se mueve mientras tanto.
        if not self.move_ready:
            if self.alpha > 0:
                self.alpha -= 4
            if self.alpha <= 0:
                self.deaths += 1
                self.alpha = 100
                self.player_x, self.player_y = self.current_respawn
                self.move_ready = True
            self.steps += 1
            return

        # 3) Movimiento del jugador (solo si moveReady).
        self._move_player(dx, dy)
        self._update_checkpoint()
        self._collect_coins()

        # 4) Victoria (en el original se chequea al tope del frame; el efecto es el
        #    mismo: con las monedas requeridas y tocando la meta, gana).
        if self._reached_goal():
            self.won = True
            self.steps += 1
            return

        # 5) Muerte por enemigo: hitTest en centro + 4 puntos medios de los lados.
        if self._touches_any_ball():
            self.move_ready = False
            self.dead = True  # marca el impacto; el respawn ocurre tras el fade

        self.steps += 1

    # ------------------------------------------------------------- movimiento
    def _decode_action(self, action) -> Tuple[int, int]:
        if isinstance(action, (tuple, list)):
            return int(action[0]), int(action[1])
        return ACTIONS[int(action)]

    def _move_player(self, dx: int, dy: int) -> None:
        speed = self.level.player_speed
        # Eje X
        if dx:
            nx = self.player_x + dx * speed
            if self._player_pos_valid(nx, self.player_y):
                self.player_x = nx
        # Eje Y
        if dy:
            ny = self.player_y + dy * speed
            if self._player_pos_valid(self.player_x, ny):
                self.player_y = ny

    def _player_pos_valid(self, cx: float, cy: float) -> bool:
        """True si el cuadrado del jugador centrado en (cx,cy) es posicion legal."""
        half = self.level.player_size / 2.0
        box = Rect(cx - half, cy - half, self.level.player_size, self.level.player_size)
        # No puede solapar ninguna pared solida.
        for w in self.level.walls:
            if box.intersects(w):
                return False
        # Debe estar contenido en el play_area (si esta definido).
        if self.level.play_area:
            if not self._box_inside_play_area(box):
                return False
        return True

    def _box_inside_play_area(self, box: Rect) -> bool:
        """El box debe estar cubierto por la union de rects jugables.

        Como los rects jugables se tocan borde con borde, basta exigir que cada
        esquina del box este dentro de algun rect y que el centro tambien lo este.
        Para corredores rectos esto es exacto.
        """
        pts = [
            (box.left, box.top), (box.right, box.top),
            (box.left, box.bottom), (box.right, box.bottom),
            ((box.left + box.right) / 2, (box.top + box.bottom) / 2),
        ]
        for (px, py) in pts:
            if not any(r.contains_point(px, py) for r in self.level.play_area):
                return False
        return True

    # ------------------------------------------------------------------ bolas
    def _init_ball(self, ball: Ball) -> BallState:
        m = ball.motion
        period = self._ball_period(ball)
        t0 = m.phase * period
        bs = BallState(x=0.0, y=0.0, radius=ball.radius, _t=t0)
        self._eval_ball(ball, bs)
        return bs

    def _ball_period(self, ball: Ball) -> float:
        m = ball.motion
        span = m.max - m.min
        if m.speed <= 0:
            return 1.0
        return 2.0 * span / m.speed  # ida + vuelta, en steps

    def _eval_ball(self, ball: Ball, bs: BallState) -> None:
        """Calcula posicion de la bola segun su patron y su tiempo interno _t."""
        m = ball.motion
        if m.type == "linear_bounce":
            span = m.max - m.min
            period = self._ball_period(ball)
            phase = (bs._t % period) / period  # 0..1
            # onda triangular: 0->1->0 mapeada a min->max->min
            tri = 1.0 - abs(2.0 * phase - 1.0)  # 0 en phase 0, 1 en phase .5, 0 en 1
            pos = m.min + tri * span
            if m.axis == "x":
                bs.x, bs.y = pos, m.fixed
            else:
                bs.x, bs.y = m.fixed, pos
        else:
            # patron desconocido -> queda estatico en (min, fixed)
            if m.axis == "x":
                bs.x, bs.y = m.min, m.fixed
            else:
                bs.x, bs.y = m.fixed, m.min

    def _update_balls(self) -> None:
        for ball, bs in zip(self.level.balls, self.balls):
            bs._t += 1.0
            self._eval_ball(ball, bs)

    # -------------------------------------------------------------- colisiones
    def _touches_any_ball(self) -> bool:
        """Replica el hitTest del original: el jugador muere si CUALQUIERA de 5
        puntos (centro + 4 medios de los lados, a _width/2) cae dentro de una bola.
        """
        half = self.level.player_size / 2.0
        px, py = self.player_x, self.player_y
        probe_points = (
            (px, py),               # centro
            (px + half, py),        # medio derecho
            (px - half, py),        # medio izquierdo
            (px, py - half),        # medio superior
            (px, py + half),        # medio inferior
        )
        for bs in self.balls:
            r2 = bs.radius ** 2
            for (qx, qy) in probe_points:
                if (bs.x - qx) ** 2 + (bs.y - qy) ** 2 <= r2:
                    return True
        return False

    def _collect_coins(self) -> None:
        half = self.level.player_size / 2.0
        for i, coin in enumerate(self.level.coins):
            if self._coin_taken[i]:
                continue
            nx = max(self.player_x - half, min(coin.x, self.player_x + half))
            ny = max(self.player_y - half, min(coin.y, self.player_y + half))
            if (coin.x - nx) ** 2 + (coin.y - ny) ** 2 <= coin.r ** 2:
                self._coin_taken[i] = True
                self.coins_collected += 1

    def _reached_goal(self) -> bool:
        goal = self.level.goal
        if goal is None:
            return False
        if self.coins_collected < self.level.coins_required:
            return False
        half = self.level.player_size / 2.0
        box = Rect(self.player_x - half, self.player_y - half,
                   self.level.player_size, self.level.player_size)
        return box.intersects(goal.rect)

    def _update_checkpoint(self) -> None:
        """Actualiza el punto de respawn si el jugador pisa un checkpoint."""
        half = self.level.player_size / 2.0
        box = Rect(self.player_x - half, self.player_y - half,
                   self.level.player_size, self.level.player_size)
        for c in self.level.checkpoints:
            if c.is_goal or c.respawn is None:
                continue
            if box.intersects(c.rect):
                self.current_respawn = c.respawn

    # ----------------------------------------------------------------- helpers
    def _spawn_point(self) -> Tuple[float, float]:
        cp = self.level.spawn_checkpoint
        if cp is not None and cp.respawn is not None:
            return cp.respawn
        return self.level.spawn

    # API util para RL ------------------------------------------------------
    def state_vector(self) -> List[float]:
        """Vector de estado plano (jugador + bolas). Util como observacion RL."""
        v = [self.player_x, self.player_y, float(self.coins_collected)]
        for bs in self.balls:
            v.extend([bs.x, bs.y])
        return v
