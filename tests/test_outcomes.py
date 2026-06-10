"""Tests de muerte, victoria, determinismo y corrida headless."""
from __future__ import annotations

import pytest


# -- Test 5: muerte (mecanica fiel al original: impacto -> fade -> respawn) ---
def test_death_on_ball_contact(engine):
    """Tocar una bola marca el impacto; tras el fade de muerte respawnea y suma death.

    Replica el original: al chocar, moveReady=false y el alpha baja 4/frame; recien
    cuando el alpha llega a 0 (DEATH_FADE_FRAMES steps) se incrementa deaths y se
    reaparece en el checkpoint.
    """
    respawn = engine.current_respawn
    deaths0 = engine.deaths

    b0 = engine.balls[0]
    engine.player_x, engine.player_y = b0.x, b0.y

    engine.step(0)  # step del impacto
    assert engine.dead is True, "deberia marcar el impacto este step"
    assert engine.move_ready is False, "deberia entrar en animacion de muerte"
    assert engine.deaths == deaths0, "la muerte aun no se contabiliza (esta en fade)"

    # Avanzar la animacion de muerte completa.
    for _ in range(engine.DEATH_FADE_FRAMES):
        engine.step(0)

    assert engine.deaths == deaths0 + 1, "tras el fade se cuenta la muerte"
    assert engine.move_ready is True, "vuelve a estar controlable tras respawnear"
    assert (engine.player_x, engine.player_y) == pytest.approx(respawn)


def test_dead_flag_is_transient(engine):
    """`dead` solo es True el step exacto del impacto."""
    b0 = engine.balls[0]
    engine.player_x, engine.player_y = b0.x, b0.y
    engine.step(0)
    assert engine.dead is True
    # El siguiente step ya esta en fade (no es un nuevo impacto).
    engine.step(0)
    assert engine.dead is False


def test_no_control_during_death_fade(engine):
    """Durante la animacion de muerte el jugador no se mueve (moveReady=false)."""
    b0 = engine.balls[0]
    engine.player_x, engine.player_y = b0.x, b0.y
    engine.step(0)  # impacto
    x_during = engine.player_x
    engine.step((1, 0))  # intentar moverse a la derecha: no debe tener efecto
    assert engine.player_x == x_during


# -- Test 6: victoria --------------------------------------------------------
def test_win_when_reaching_goal(engine, level1_data):
    """Teleportar a la meta (check2) con coins_required satisfecho -> won."""
    goal = engine.level.goal
    assert goal is not None and goal.is_goal
    g = goal.rect
    # Centro de la meta, garantiza interseccion del box del jugador.
    engine.player_x = (g.left + g.right) / 2.0
    engine.player_y = (g.top + g.bottom) / 2.0

    assert engine.coins_collected >= engine.level.coins_required
    engine.step(0)
    assert engine.won is True


def test_win_requires_coins_when_required(engine, level1):
    """Si coins_required > 0 y faltan monedas, NO gana.

    El nivel 1 tiene coins_required=0 (siempre cumplido). Parametrizamos
    forzando el requisito a 1 sobre un Level clonado para documentar la regla.
    """
    from dataclasses import replace
    from engine import GameEngine

    # Nivel 1 real: requisito 0 -> gana sin monedas (ya cubierto arriba).
    assert level1.coins_required == 0

    # Variante con requisito 1: no debe ganar al pisar la meta sin monedas.
    harder = replace(level1, coins_required=1)
    eng = GameEngine(harder)
    g = eng.level.goal.rect
    eng.player_x = (g.left + g.right) / 2.0
    eng.player_y = (g.top + g.bottom) / 2.0
    eng.step(0)
    assert eng.won is False, "no deberia ganar con monedas insuficientes"


# -- Test 7: determinismo ----------------------------------------------------
def test_determinism_same_actions_same_state(level1):
    """Dos engines con la misma secuencia producen el mismo state_vector()."""
    from engine import GameEngine

    e1 = GameEngine(level1)
    e2 = GameEngine(level1)

    actions = [1, 1, 4, 6, 0, 3, 2, 8, 1, 4] * 20  # 200 acciones variadas
    for a in actions:
        e1.step(a)
        e2.step(a)

    assert e1.state_vector() == e2.state_vector()
    assert e1.steps == e2.steps
    assert e1.deaths == e2.deaths


# -- Test headless -----------------------------------------------------------
@pytest.mark.headless
def test_headless_500_steps_no_exception(engine):
    """Corre 500 steps con accion 0 sin lanzar excepciones."""
    for _ in range(500):
        engine.step(0)
    assert engine.steps == 500
    # state_vector siempre numerico y de tamano estable
    sv = engine.state_vector()
    assert len(sv) == 3 + 2 * len(engine.balls)
    assert all(isinstance(x, float) for x in sv)
