"""Captura headless de un nivel renderizado por el motor del puerto.

Carga un nivel JSON, crea GameEngine + Renderer (pygame en modo dummy/headless),
avanza K steps para posicionar las bolas, dibuja en un Surface del tamano del
nivel y guarda a PNG.

Uso:
    python capture_level.py --level src/levels/level_01.json --out out.png --steps 0
"""
from __future__ import annotations

import argparse
import os
import sys

# Headless ANTES de importar pygame.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

# Permitir importar engine/level/render desde src/.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import pygame  # noqa: E402

from engine import GameEngine  # noqa: E402
from level import Level  # noqa: E402
from render import Renderer  # noqa: E402


def capture(level_path: str, out_path: str, steps: int = 0, scale: float = 1.0,
            hud: bool = False) -> str:
    pygame.init()
    try:
        pygame.font.init()
    except Exception:
        pass

    level = Level.load(level_path)
    engine = GameEngine(level)
    for _ in range(max(0, steps)):
        engine.step(0)  # accion 0 = quieto, solo avanza las bolas

    renderer = Renderer(engine, scale=scale)
    surface = pygame.Surface((renderer.width, renderer.height))
    renderer.draw(surface)
    if hud:
        renderer.draw_hud(surface)

    out_dir = os.path.dirname(os.path.abspath(out_path))
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir, exist_ok=True)
    pygame.image.save(surface, out_path)
    pygame.quit()
    return out_path


def _resolve(path: str) -> str:
    if os.path.isabs(path):
        return path
    # rutas relativas se resuelven contra la raiz del repo
    return os.path.join(_ROOT, path)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Captura PNG headless de un nivel.")
    p.add_argument("--level", required=True, help="ruta al JSON del nivel")
    p.add_argument("--out", required=True, help="ruta del PNG de salida")
    p.add_argument("--steps", type=int, default=0, help="steps a avanzar (default 0)")
    p.add_argument("--scale", type=float, default=1.0, help="escala de render")
    p.add_argument("--hud", action="store_true", help="dibujar barras HUD")
    args = p.parse_args(argv)

    out = capture(_resolve(args.level), _resolve(args.out), steps=args.steps,
                  scale=args.scale, hud=args.hud)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
