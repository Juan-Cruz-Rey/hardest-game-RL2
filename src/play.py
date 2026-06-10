"""Punto de entrada jugable. Carga un nivel JSON y lo hace interactivo.

Uso:
    python play.py                     # carga levels/level_01.json
    python play.py levels/level_01.json
    python play.py --scale 1.5

Controles: flechas o WASD para mover, R para reiniciar, Esc para salir.
La simulacion (engine) y el render estan separados: el engine avanza un step de
fisica por frame; el render solo dibuja el estado.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pygame

from engine import GameEngine
from level import Level
from render import Renderer

# El SWF original corre a 30 fps (frameRate=30 en el header) y la velocidad de
# bolas/jugador esta calibrada POR FRAME del SWF. Para reproducir la velocidad real
# hay que avanzar la fisica a 30 steps/segundo, no 60 (si no, todo va al doble).
FPS = 30


def resolve_level_path(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    return Path(__file__).parent / "levels" / "level_01.json"


def action_from_keys(keys) -> tuple:
    dx = dy = 0
    if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
        dx += 1
    if keys[pygame.K_LEFT] or keys[pygame.K_a]:
        dx -= 1
    if keys[pygame.K_UP] or keys[pygame.K_w]:
        dy -= 1
    if keys[pygame.K_DOWN] or keys[pygame.K_s]:
        dy += 1
    return (dx, dy)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("level", nargs="?", default=None, help="ruta al JSON del nivel")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--sim-hz", type=int, default=FPS, dest="sim_hz",
                    help="ticks de simulacion por segundo (30 = tick del SWF original)")
    ap.add_argument("--fps", type=int, default=FPS,
                    help="fps de render (la fisica sigue corriendo a --sim-hz)")
    args = ap.parse_args()

    level = Level.load(resolve_level_path(args.level))
    engine = GameEngine(level)
    renderer = Renderer(engine, scale=args.scale)

    pygame.init()
    pygame.display.set_caption(f"World's Hardest Game - {level.name}")
    screen = pygame.display.set_mode((renderer.width, renderer.height))
    clock = pygame.time.Clock()

    # Fixed timestep: la SIMULACION avanza a `sim_hz` ticks/segundo (30 = tick del
    # SWF original), desacoplada del framerate de RENDER. Asi la velocidad real del
    # juego es identica al original aunque el display corra a otros fps.
    sim_dt = 1.0 / args.sim_hz
    accumulator = 0.0
    render_fps = max(args.fps, args.sim_hz)

    running = True
    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    running = False
                elif ev.key == pygame.K_r:
                    engine.reset()

        dt = clock.tick(render_fps) / 1000.0
        accumulator += dt
        # Evita la "espiral de la muerte" si hubo un freeze: techo de ticks por frame.
        max_ticks = 5
        ticks = 0
        action = action_from_keys(pygame.key.get_pressed())
        while accumulator >= sim_dt and ticks < max_ticks:
            engine.step(action)
            accumulator -= sim_dt
            ticks += 1

        renderer.draw(screen)
        renderer.draw_hud(screen)
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
