"""Carga y modelo de datos de un nivel desde JSON.

Define las estructuras inmutables que describen un nivel (geometria, jugador,
checkpoints, bolas). NO contiene logica de simulacion ni de render: solo data.
El motor (`engine.py`) consume estas estructuras.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass(frozen=True)
class Rect:
    """Rectangulo axis-aligned. (x, y) = esquina superior-izquierda."""
    x: float
    y: float
    w: float
    h: float

    @property
    def left(self) -> float:
        return self.x

    @property
    def top(self) -> float:
        return self.y

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h

    def contains_point(self, px: float, py: float) -> bool:
        return self.left <= px <= self.right and self.top <= py <= self.bottom

    def intersects(self, other: "Rect") -> bool:
        return not (
            self.right < other.left
            or self.left > other.right
            or self.bottom < other.top
            or self.top > other.bottom
        )

    @classmethod
    def from_dict(cls, d: dict) -> "Rect":
        return cls(float(d["x"]), float(d["y"]), float(d["w"]), float(d["h"]))


@dataclass(frozen=True)
class BallMotion:
    """Parametros del patron de movimiento de una bola.

    Patron `linear_bounce`: la bola va y vuelve entre `min` y `max` sobre `axis`,
    a `speed` px/step, manteniendo `fixed` en el otro eje. `phase` (0..1) define
    la posicion inicial dentro del ciclo ida-vuelta (0 = en `min` yendo a `max`).
    """
    type: str
    axis: str
    min: float
    max: float
    fixed: float
    speed: float
    phase: float = 0.0

    @classmethod
    def from_dict(cls, d: dict) -> "BallMotion":
        return cls(
            type=d.get("type", "linear_bounce"),
            axis=d.get("axis", "x"),
            min=float(d["min"]),
            max=float(d["max"]),
            fixed=float(d["fixed"]),
            speed=float(d["speed"]),
            phase=float(d.get("phase", 0.0)),
        )


@dataclass(frozen=True)
class Ball:
    radius: float
    motion: BallMotion

    @classmethod
    def from_dict(cls, d: dict) -> "Ball":
        return cls(radius=float(d["radius"]), motion=BallMotion.from_dict(d["motion"]))


@dataclass(frozen=True)
class Checkpoint:
    id: str
    rect: Rect
    is_spawn: bool = False
    is_goal: bool = False
    respawn: Optional[tuple] = None  # (x, y) centro de reaparicion

    @classmethod
    def from_dict(cls, d: dict) -> "Checkpoint":
        respawn = None
        if d.get("respawn"):
            respawn = (float(d["respawn"]["x"]), float(d["respawn"]["y"]))
        return cls(
            id=d["id"],
            rect=Rect.from_dict(d["rect"]),
            is_spawn=bool(d.get("is_spawn", False)),
            is_goal=bool(d.get("is_goal", False)),
            respawn=respawn,
        )


@dataclass(frozen=True)
class Coin:
    x: float
    y: float
    r: float = 6.0

    @classmethod
    def from_dict(cls, d: dict) -> "Coin":
        return cls(float(d["x"]), float(d["y"]), float(d.get("r", 6.0)))


@dataclass(frozen=True)
class Level:
    name: str
    level_index: int
    width: float
    height: float
    player_size: float
    player_speed: float
    spawn: tuple  # (x, y) centro
    coins_required: int
    play_area: List[Rect] = field(default_factory=list)
    walls: List[Rect] = field(default_factory=list)
    checkpoints: List[Checkpoint] = field(default_factory=list)
    coins: List[Coin] = field(default_factory=list)
    balls: List[Ball] = field(default_factory=list)

    @property
    def goal(self) -> Optional[Checkpoint]:
        for c in self.checkpoints:
            if c.is_goal:
                return c
        return None

    @property
    def spawn_checkpoint(self) -> Optional[Checkpoint]:
        for c in self.checkpoints:
            if c.is_spawn:
                return c
        return self.checkpoints[0] if self.checkpoints else None

    @classmethod
    def from_dict(cls, d: dict) -> "Level":
        area = d["area"]
        player = d["player"]
        return cls(
            name=d.get("name", "Level"),
            level_index=int(d.get("level_index", 0)),
            width=float(area["width"]),
            height=float(area["height"]),
            player_size=float(player["size"]),
            player_speed=float(player["speed"]),
            spawn=(float(player["spawn"]["x"]), float(player["spawn"]["y"])),
            coins_required=int(d.get("coins_required", 0)),
            play_area=[Rect.from_dict(r) for r in d.get("play_area", [])],
            walls=[Rect.from_dict(r) for r in d.get("walls", [])],
            checkpoints=[Checkpoint.from_dict(c) for c in d.get("checkpoints", [])],
            coins=[Coin.from_dict(c) for c in d.get("coins", [])],
            balls=[Ball.from_dict(b) for b in d.get("balls", [])],
        )

    @classmethod
    def load(cls, path) -> "Level":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)
