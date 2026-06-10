"""Tests del jugador: spawn, confinamiento al play_area y movimiento."""
from __future__ import annotations

import pytest


# -- Test 4: spawn + confinamiento -------------------------------------------
def test_player_spawn(engine, level1_data):
    spawn = level1_data["player"]["spawn"]
    assert engine.player_x == pytest.approx(spawn["x"])
    assert engine.player_y == pytest.approx(spawn["y"])


def test_player_cannot_leave_play_area_left_corridor(engine):
    """En el corredor izquierdo (vertical) empujar arriba/abajo topa con la pared.

    Spawn (87,200), play_area izq y=[127,272], player half=6 -> Y legal
    en [133, 266]. Empujar mucho hacia arriba/abajo no debe salir del rango.
    """
    half = engine.level.player_size / 2.0
    # rect del corredor izquierdo = primer play_area rect
    left = engine.level.play_area[0]
    y_min, y_max = left.top + half, left.bottom - half

    # Empujar hacia arriba un monton de steps.
    for _ in range(100):
        engine.step((0, -1))
    assert engine.player_y >= y_min - 1e-6, engine.player_y
    # y nunca atraveso el borde superior
    assert engine.player_y == pytest.approx(y_min, abs=engine.level.player_speed)

    engine.reset()
    for _ in range(100):
        engine.step((0, 1))
    assert engine.player_y <= y_max + 1e-6, engine.player_y
    assert engine.player_y == pytest.approx(y_max, abs=engine.level.player_speed)


def test_player_cannot_leave_against_left_wall(engine):
    """Empujar a la izquierda topa con el borde izquierdo del play_area."""
    half = engine.level.player_size / 2.0
    left = engine.level.play_area[0]
    x_min = left.left + half
    for _ in range(100):
        engine.step((-1, 0))
    assert engine.player_x >= x_min - 1e-6
    assert engine.player_x == pytest.approx(x_min, abs=engine.level.player_speed)


def test_player_stays_inside_center_corridor(engine):
    """Recorriendo el corredor central, cada posicion es legal (dentro del play_area)."""
    # Llevar al jugador al corredor central y barrerlo a la derecha.
    for _ in range(300):
        engine.step((1, 0))
        # invariante: el jugador siempre esta en una posicion valida
        assert engine._player_pos_valid(engine.player_x, engine.player_y)


# -- Test 8: movimiento exacto N*speed ---------------------------------------
def test_move_exact_distance_with_free_space(engine):
    """Accion (1,0) durante N steps mueve N*speed en X mientras haya espacio.

    Posicionamos al jugador en una zona libre conocida del corredor central
    (lejos de paredes y de las filas de bolas) y verificamos el desplazamiento
    exacto. La fila central libre de bolas esta a media altura entre dos filas.
    """
    speed = engine.level.player_speed
    center = engine.level.play_area[1]  # cuerpo central x[152,397] y[152,247]
    half = engine.level.player_size / 2.0

    # Punto de partida en el corredor central, en una franja sin bola (entre las
    # filas y=200..213): y=200 esta libre de balls (que estan en 163/188/213/238).
    engine.player_x = center.left + half + 5
    engine.player_y = 200.0
    x0 = engine.player_x
    y0 = engine.player_y
    max_x = center.right - half

    n = 10
    assert x0 + n * speed < max_x, "el test asume que hay espacio libre"
    for _ in range(n):
        engine.step((1, 0))
    assert engine.player_x == pytest.approx(x0 + n * speed, abs=1e-9)
    assert engine.player_y == pytest.approx(y0, abs=1e-9)
