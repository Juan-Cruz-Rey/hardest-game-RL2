"""Configuracion de pytest para la suite headless.

Los modulos del motor viven en `src/` y se importan SIN paquete
(`from level import ...`), asi que insertamos `src/` en sys.path antes de
importar nada. Tambien exponemos fixtures comunes: el path al JSON del nivel 1,
el `Level` cargado y un `GameEngine` fresco.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# --- rootdir / import path -------------------------------------------------
TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
SRC_DIR = REPO_ROOT / "src"

# src/ al frente para que `import engine` / `from level import ...` funcione.
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

LEVEL1_JSON = SRC_DIR / "levels" / "level_01.json"


@pytest.fixture(scope="session")
def level1_path() -> Path:
    assert LEVEL1_JSON.exists(), f"No existe el nivel 1: {LEVEL1_JSON}"
    return LEVEL1_JSON


@pytest.fixture(scope="session")
def level1_data(level1_path: Path) -> dict:
    """Diccionario crudo del JSON, para asserts data-driven sin hardcodear."""
    import json
    return json.loads(level1_path.read_text(encoding="utf-8"))


@pytest.fixture
def level1(level1_path: Path):
    """Objeto Level (recargado por test para evitar estado compartido)."""
    from level import Level
    return Level.load(level1_path)


@pytest.fixture
def engine(level1):
    """GameEngine fresco sobre el nivel 1."""
    from engine import GameEngine
    return GameEngine(level1)
