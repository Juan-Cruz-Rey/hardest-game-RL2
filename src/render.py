"""Render con pygame. Solo LEE el estado de `GameEngine`; no muta nada.

Separado de la simulacion para poder correr `engine.step()` sin pygame (headless
para RL). Reproduce la paleta del original: fondo lavanda, corredor a cuadros,
cuadros verdes de checkpoint, bolas azules con borde, cuadrado rojo.
"""
from __future__ import annotations

import pygame

from engine import GameEngine
from level import Level

# Paleta EXACTA del original (muestreada del SWF render, frame 61).
COL_BG = (180, 181, 254)        # lavanda de fondo
COL_PLAY_A = (230, 230, 255)    # cuadros claros del corredor
COL_PLAY_B = (247, 247, 255)    # cuadros oscuros del corredor (azulado, contraste sutil)
COL_GREEN = (181, 254, 180)     # zonas de checkpoint
COL_PLAYER = (255, 0, 0)        # cuadrado rojo (puro)
COL_PLAYER_EDGE = (0, 0, 0)
COL_BALL = (0, 0, 255)          # relleno bola azul (puro)
COL_BALL_EDGE = (0, 0, 0)       # borde bola
COL_COIN = (250, 210, 40)
COL_COIN_EDGE = (120, 90, 0)
COL_WALL = (0, 0, 0)
COL_TEXT = (255, 255, 255)
COL_BAR = (0, 0, 0)

CHECKER = 25       # tamano del cuadro del piso
WALL_THICKNESS = 2  # grosor del borde negro exterior (px del nivel, igual al original)


class Renderer:
    def __init__(self, engine: GameEngine, scale: float = 1.0, bar_h: int = 26):
        self.engine = engine
        self.level: Level = engine.level
        self.scale = scale
        self.bar_h = bar_h
        self.width = int(self.level.width * scale)
        self.height = int(self.level.height * scale)
        self._font = None

    def ensure_font(self):
        if self._font is None:
            self._font = pygame.font.SysFont("Arial", 16, bold=True)
        return self._font

    def _s(self, v: float) -> int:
        return int(v * self.scale)

    def draw(self, surface: pygame.Surface) -> None:
        e = self.engine
        lvl = self.level
        surface.fill(COL_BG)

        # Piso a cuadros: grilla GLOBAL (alineada al origen del nivel) recortada a
        # cada rect del play_area, para que los cuadros queden continuos entre rects
        # (como el original) y no reinicien en cada rect.
        for rect in lvl.play_area:
            self._draw_checker(surface, rect)

        # Zonas verdes de checkpoint ENCIMA del checker: las camaras de inicio/meta
        # son verde liso en el original (sin cuadros).
        for c in lvl.checkpoints:
            pygame.draw.rect(surface, COL_GREEN, self._rect_px(c.rect))

        # Paredes solidas explicitas.
        for w in lvl.walls:
            pygame.draw.rect(surface, COL_WALL, self._rect_px(w))

        # Contorno negro de la UNION de zonas jugables (corredor + verdes): solo en
        # los bordes externos. Se cachea (es estatico) y se blittea cada frame.
        surface.blit(self._outline_surf(), (0, 0))

        # Monedas.
        for i, coin in enumerate(lvl.coins):
            if e._coin_taken[i]:
                continue
            pos = (self._s(coin.x), self._s(coin.y))
            pygame.draw.circle(surface, COL_COIN, pos, self._s(coin.r))
            pygame.draw.circle(surface, COL_COIN_EDGE, pos, self._s(coin.r), 2)

        # Bolas: anillo negro grueso + nucleo azul puro (como el original).
        for bs in e.balls:
            pos = (self._s(bs.x), self._s(bs.y))
            r = self._s(bs.radius)
            pygame.draw.circle(surface, COL_BALL_EDGE, pos, r)          # anillo negro
            pygame.draw.circle(surface, COL_BALL, pos, max(1, r - 3))   # nucleo azul

        # Jugador (cuadrado rojo).
        half = lvl.player_size / 2.0
        pr = pygame.Rect(
            self._s(e.player_x - half), self._s(e.player_y - half),
            self._s(lvl.player_size), self._s(lvl.player_size),
        )
        pygame.draw.rect(surface, COL_PLAYER, pr)
        pygame.draw.rect(surface, COL_PLAYER_EDGE, pr, 2)

    def draw_hud(self, surface: pygame.Surface) -> None:
        """Barras superior/inferior con texto, como el original."""
        font = self.ensure_font()
        e = self.engine
        # Barra superior.
        pygame.draw.rect(surface, COL_BAR, (0, 0, self.width, self.bar_h))
        lvl_txt = f"{e.level.level_index}/30"
        surface.blit(font.render(f"LEVEL: {lvl_txt}", True, COL_TEXT), (8, 5))
        if e.level.coins_required:
            ctxt = f"COINS: {e.coins_collected}/{e.level.coins_required}"
            surface.blit(font.render(ctxt, True, COL_TEXT), (self.width // 2 - 40, 5))
        # Barra inferior.
        by = self.height - self.bar_h
        pygame.draw.rect(surface, COL_BAR, (0, by, self.width, self.bar_h))
        surface.blit(font.render(f"DEATHS: {e.deaths}", True, COL_TEXT), (8, by + 5))
        if e.won:
            msg = font.render("LEVEL COMPLETE!", True, (120, 255, 120))
            surface.blit(msg, (self.width - 180, by + 5))

    def _rect_px(self, r) -> pygame.Rect:
        return pygame.Rect(self._s(r.x), self._s(r.y), self._s(r.w), self._s(r.h))

    def _draw_checker(self, surface, rect) -> None:
        """Dibuja el piso a cuadros dentro de `rect` usando una grilla GLOBAL.

        Los indices de cuadro se calculan respecto al origen del nivel (0,0), no
        respecto al rect, de modo que cuadros adyacentes entre rects distintos
        queden continuos (igual que el original).
        """
        step = self._s(CHECKER)
        if step <= 0:
            return
        rx0, ry0 = self._s(rect.x), self._s(rect.y)
        rx1, ry1 = self._s(rect.right), self._s(rect.bottom)
        clip = surface.get_clip()
        surface.set_clip(pygame.Rect(rx0, ry0, rx1 - rx0, ry1 - ry0))
        # Primer indice de grilla global que cubre el rect.
        ix0 = rx0 // step
        iy0 = ry0 // step
        iy = iy0
        y = iy * step
        while y < ry1:
            ix = ix0
            x = ix * step
            while x < rx1:
                col = COL_PLAY_A if (ix + iy) % 2 == 0 else COL_PLAY_B
                pygame.draw.rect(surface, col, (x, y, step, step))
                x += step
                ix += 1
            y += step
            iy += 1
        surface.set_clip(clip)

    def _outline_surf(self) -> pygame.Surface:
        """Surface transparente con el contorno externo de la union de zonas jugables.

        Se computa una sola vez (la geometria es estatica) y se cachea.
        """
        if getattr(self, "_outline_cache", None) is not None:
            return self._outline_cache
        import numpy as np
        rects = self.level.play_area + [c.rect for c in self.level.checkpoints]
        w, h = self.width, self.height
        thickness = self._s(WALL_THICKNESS)  # grosor del borde en px de pantalla
        mask = np.zeros((h, w), dtype=bool)
        for r in rects:
            x0, y0 = max(0, self._s(r.x)), max(0, self._s(r.y))
            x1, y1 = min(w, self._s(r.right)), min(h, self._s(r.bottom))
            mask[y0:y1, x0:x1] = True
        # Borde EXTERIOR pegado al limite, como la pared negra del original. El
        # original lo dibuja ~1px mas afuera del rect jugable, asi que dilatamos
        # 1px extra (thickness+1) para alinear y luego restamos la mascara.
        dil = mask.copy()
        for _ in range(thickness + 1):
            e = dil.copy()
            e[1:, :] |= dil[:-1, :]
            e[:-1, :] |= dil[1:, :]
            e[:, 1:] |= dil[:, :-1]
            e[:, :-1] |= dil[:, 1:]
            dil = e
        # interior = mascara dilatada 1px (para que el anillo arranque 1px afuera).
        grow1 = mask.copy()
        e = grow1.copy()
        e[1:, :] |= grow1[:-1, :]
        e[:-1, :] |= grow1[1:, :]
        e[:, 1:] |= grow1[:, :-1]
        e[:, :-1] |= grow1[:, 1:]
        grow1 = e
        edge = dil & ~grow1  # anillo de `thickness` px, empezando 1px afuera del rect
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        rgba = np.zeros((w, h, 4), dtype=np.uint8)  # surfarray es (x, y)
        edge_xy = edge.T  # -> (w, h)
        rgba[edge_xy] = (*COL_WALL, 255)
        pygame.surfarray.blit_array(surf, rgba[:, :, :3])
        # canal alpha
        alpha = np.zeros((w, h), dtype=np.uint8)
        alpha[edge_xy] = 255
        pygame.surfarray.pixels_alpha(surf)[:, :] = alpha
        self._outline_cache = surf
        return surf
