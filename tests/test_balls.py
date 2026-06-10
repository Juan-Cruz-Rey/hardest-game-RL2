"""Tests de la fisica de las bolas (data-driven contra level_01.json)."""
from __future__ import annotations

import math

import pytest


def _ball_period(motion: dict) -> float:
    """Periodo (ida+vuelta) en steps, igual que engine._ball_period."""
    span = motion["max"] - motion["min"]
    speed = motion["speed"]
    if speed <= 0:
        return 1.0
    return 2.0 * span / speed


# -- Test 1: bola 0 periodica ------------------------------------------------
def test_ball0_start_and_period(engine, level1_data):
    """La bola 0 arranca en (156, 238) y tras un periodo completo vuelve a ~origen."""
    motion = level1_data["balls"][0]["motion"]
    start_x = motion["min"]          # phase 0 => en min
    fixed_y = motion["fixed"]

    b0 = engine.balls[0]
    assert b0.x == pytest.approx(start_x, abs=0.7)
    assert b0.y == pytest.approx(fixed_y, abs=1e-9)

    period_f = _ball_period(motion)
    period = int(round(period_f))
    assert period == 72, f"periodo esperado 72 steps, calculado {period_f}"

    sx, sy = b0.x, b0.y
    for _ in range(period):
        engine.step(0)
    assert engine.balls[0].x == pytest.approx(sx, abs=0.7)
    assert engine.balls[0].y == pytest.approx(sy, abs=1e-9)


# -- Test 2: rango en X y Y fija ---------------------------------------------
def test_balls_stay_in_x_range_and_fixed_y(engine, level1_data):
    """Las 4 bolas se mueven en X dentro de [min, max] y mantienen su Y fija."""
    motions = [b["motion"] for b in level1_data["balls"]]
    eps = 1e-6

    # Muestreamos mas de un periodo completo.
    for _ in range(150):
        for i, bs in enumerate(engine.balls):
            m = motions[i]
            assert m["min"] - eps <= bs.x <= m["max"] + eps, (
                f"bola {i} x={bs.x} fuera de [{m['min']},{m['max']}]"
            )
            assert bs.y == pytest.approx(m["fixed"], abs=1e-9), (
                f"bola {i} cambio su Y fija {m['fixed']} -> {bs.y}"
            )
        engine.step(0)


# -- Test 3: fases opuestas --------------------------------------------------
def test_opposite_phases_at_t0(engine, level1_data):
    """A t=0: phase 0 cerca de min, phase 0.5 cerca de max."""
    motions = [b["motion"] for b in level1_data["balls"]]
    for i, bs in enumerate(engine.balls):
        m = motions[i]
        if m["phase"] == pytest.approx(0.0):
            assert bs.x == pytest.approx(m["min"], abs=0.7), (
                f"bola {i} fase 0 deberia estar en min={m['min']}, esta en {bs.x}"
            )
        elif m["phase"] == pytest.approx(0.5):
            assert bs.x == pytest.approx(m["max"], abs=0.7), (
                f"bola {i} fase .5 deberia estar en max={m['max']}, esta en {bs.x}"
            )
        else:  # pragma: no cover - el nivel 1 solo usa 0 y 0.5
            pytest.skip(f"fase no contemplada: {m['phase']}")
