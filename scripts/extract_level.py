#!/usr/bin/env python3
"""Extractor reutilizable de niveles para "The World's Hardest Game".

Genera los JSON data-driven que consume el motor (src/engine.py) a partir del
dump XML del SWF decompilado con JPEXS ffdec
(decompiled/swf.xml).

Que hace, en una pasada:

  1. Localiza, para un nivel N, las instancias nombradas (`walls`, `enemies`,
     `check1`, `check2`, `check3`, `check4`) que el main timeline coloca para
     ese nivel, junto con su `characterId` y su matriz de colocacion (en twips).
     El nivel N corresponde al grupo con `ratio == 60 + (N-1)*4`
     (equivalente a `frame == 61 + (N-1)*4`, el ratio es frame-1).
     Si un mismo nombre aparece mas de una vez en el grupo se toma el de
     menor characterId (regla "menor id por nombre").

  2. Reconstruye la trayectoria por-frame de cada bola del clip `enemies`
     (un DefineSpriteTag) leyendo sus matrices PlaceObject2 (incluyendo los
     tags 'move' que solo reescriben la matriz por depth) y detecta el patron
     `linear_bounce` (axis, min, max, fixed, speed, phase) en coordenadas de
     pantalla (px).

  3. Deriva geometria aproximada de checkpoints (rect = shape bounds * escala,
     centrada en la translacion de la instancia) y deja TODOs claros para la
     geometria fina de walls / play_area (que conviene refinar midiendo el PNG
     del frame correspondiente: decompiled/frames/{frame}.png).

  4. Escribe un JSON valido segun src/levels/schema.md.

Coordenadas: el SWF trabaja en twips (1 px = 20 twips). Las posiciones en
pantalla se obtienen sumando el origen del clip (en px) al offset local (en px).
Para el clip `enemies` del nivel 1 el origen en pantalla es (164, 238) px, que
es la translacion de la instancia `enemies` (3280, 4760 twips) / 20.

CLI:
    python extract_level.py --level 1 --out salida.json
    python extract_level.py --level 1 --verify   # compara bolas vs level_01.json

Solo usa stdlib (+ opcionalmente nada mas). No toca el motor ni los JSON
existentes.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# --------------------------------------------------------------------------- #
# Rutas por defecto (relativas a la raiz del repo)
# --------------------------------------------------------------------------- #

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DEFAULT_SWF_XML = os.path.join(REPO, "decompiled", "swf.xml")
DEFAULT_LEVELS_DIR = os.path.join(REPO, "src", "levels")
DEFAULT_FRAMES_DIR = os.path.join(REPO, "decompiled", "frames")

TWIPS = 20.0  # 1 px = 20 twips

# Origen en pantalla (px) del clip `enemies` para los niveles "estandar".
# = translacion de la instancia `enemies` / 20. Para nivel 1: (3280,4760)/20.
# Se recalcula por-nivel desde la matriz de la instancia, este es el fallback.
DEFAULT_ENEMIES_ORIGIN = (164.0, 238.0)

AREA = {"width": 550, "height": 400}
PLAYER_SIZE = 12
PLAYER_SPEED = 3.0
BALL_RADIUS = 8  # radio visible del circulo azul en px (schema)


# --------------------------------------------------------------------------- #
# Utilidades de parseo del XML (texto plano, sin DOM, para el archivo de 11 MB)
# --------------------------------------------------------------------------- #


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


_ATTR_RE = re.compile(r'(\w+)="([^"]*)"')


def parse_attrs(tag_text: str) -> Dict[str, str]:
    """Devuelve {attr: value} de la cadena de atributos de un tag <item ...>."""
    return dict(_ATTR_RE.findall(tag_text))


def find_balanced_subtags(text: str, open_pos: int) -> Tuple[int, int]:
    """Dado el indice donde empieza un bloque <subTags>, devuelve (start, end)
    del contenido interno (entre <subTags> y su </subTags> balanceado).

    Maneja anidamiento de <subTags> (sprites dentro de sprites).
    """
    open_tag = "<subTags>"
    close_tag = "</subTags>"
    start = text.index(open_tag, open_pos) + len(open_tag)
    depth = 1
    i = start
    while depth > 0:
        no = text.find(open_tag, i)
        nc = text.find(close_tag, i)
        if nc == -1:
            raise ValueError("subTags sin cierre balanceado")
        if no != -1 and no < nc:
            depth += 1
            i = no + len(open_tag)
        else:
            depth -= 1
            i = nc + len(close_tag)
            if depth == 0:
                return start, nc
    raise ValueError("no se pudo balancear subTags")


def extract_sprite_subtags(swf_xml: str, sprite_id: int) -> str:
    """Devuelve el texto interno de <subTags>...</subTags> del DefineSpriteTag
    cuyo spriteId == sprite_id. Usa la tecnica de busqueda de 'spriteId="N">'
    y escaneo balanceado pedida en los requisitos.
    """
    needle = f'spriteId="{sprite_id}">'
    pos = swf_xml.find(needle)
    if pos == -1:
        # Algunos tags tienen mas atributos despues de spriteId; buscar variante.
        m = re.search(rf'<item type="DefineSpriteTag"[^>]*spriteId="{sprite_id}"', swf_xml)
        if not m:
            raise KeyError(f"No se encontro DefineSpriteTag spriteId={sprite_id}")
        pos = m.start()
    start, end = find_balanced_subtags(swf_xml, pos)
    return swf_xml[start:end]


# --------------------------------------------------------------------------- #
# Modelo de tags PlaceObject2
# --------------------------------------------------------------------------- #


@dataclass
class Place:
    depth: int
    character_id: Optional[int]
    name: Optional[str]
    is_move: bool
    has_char: bool
    has_matrix: bool
    translate_x: float  # twips
    translate_y: float  # twips
    scale_x: float
    scale_y: float
    ratio: Optional[int]
    raw_attrs: Dict[str, str] = field(default_factory=dict)


_PLACE_RE = re.compile(
    r'<item type="PlaceObject2Tag"([^>]*?)(/>|>(.*?)</item>)',
    re.DOTALL,
)
_MATRIX_RE = re.compile(r'<matrix type="MATRIX"([^>]*)/>')


def _matrix_from_inner(inner: str) -> Tuple[float, float, float, float]:
    m = _MATRIX_RE.search(inner or "")
    if not m:
        return 0.0, 0.0, 1.0, 1.0
    a = parse_attrs(m.group(1))
    tx = float(a.get("translateX", "0"))
    ty = float(a.get("translateY", "0"))
    sx = float(a.get("scaleX", "1")) if a.get("hasScale") == "true" else 1.0
    sy = float(a.get("scaleY", "1")) if a.get("hasScale") == "true" else 1.0
    return tx, ty, sx, sy


def iter_places(block: str) -> List["TimelineEvent"]:
    """Parsea un bloque (subTags de un sprite, o el main timeline) y devuelve
    una lista ordenada de eventos: Place(...) o 'SHOWFRAME'.
    Mantener el orden y los ShowFrame es lo que permite reconstruir la posicion
    por-frame de cada depth.
    """
    events: List[TimelineEvent] = []
    # Recorremos en orden de aparicion tanto PlaceObject2 como ShowFrame.
    token_re = re.compile(
        r'<item type="PlaceObject2Tag"([^>]*?)(/>|>(.*?)</item>)'
        r'|<item type="ShowFrameTag"[^>]*/>',
        re.DOTALL,
    )
    for m in token_re.finditer(block):
        if m.group(0).startswith('<item type="ShowFrameTag"'):
            events.append("SHOWFRAME")
            continue
        attrs = parse_attrs(m.group(1))
        inner = m.group(3) or ""
        tx, ty, sx, sy = _matrix_from_inner(inner)
        cid = attrs.get("characterId")
        ratio = attrs.get("ratio")
        events.append(
            Place(
                depth=int(attrs.get("depth", "0")),
                character_id=int(cid) if cid is not None else None,
                name=attrs.get("name"),
                is_move=attrs.get("placeFlagMove") == "true",
                has_char=attrs.get("placeFlagHasCharacter") == "true",
                has_matrix=attrs.get("placeFlagHasMatrix") == "true",
                translate_x=tx,
                translate_y=ty,
                scale_x=sx,
                scale_y=sy,
                ratio=int(ratio) if ratio is not None else None,
                raw_attrs=attrs,
            )
        )
    return events


TimelineEvent = object  # Place | "SHOWFRAME"


# --------------------------------------------------------------------------- #
# 1) Trayectorias de bolas  ->  patron linear_bounce
# --------------------------------------------------------------------------- #


def _positions_per_depth(events: List[TimelineEvent]) -> Dict[int, List[Tuple[float, float]]]:
    """Simula el display list del sprite frame a frame y devuelve, por cada
    depth, la lista de (translateX, translateY) en twips, una entrada por frame.
    """
    current: Dict[int, Tuple[float, float]] = {}
    series: Dict[int, List[Tuple[float, float]]] = {}
    started = False
    for ev in events:
        if ev == "SHOWFRAME":
            started = True
            for d, pos in current.items():
                series.setdefault(d, []).append(pos)
            continue
        p: Place = ev  # type: ignore
        if not p.has_matrix:
            continue
        # Place (con o sin character) o Move: en ambos casos fija la matriz del depth.
        current[p.depth] = (p.translate_x, p.translate_y)
    # Si no hubo ShowFrame final, no pasa nada: ya capturamos todos los frames.
    return series


def _detect_linear_bounce(
    xs: List[float],
    ys: List[float],
    origin_px: Tuple[float, float],
) -> Optional[dict]:
    """Dada la serie de posiciones (twips) de UNA bola a lo largo del periodo,
    detecta el patron de rebote lineal y devuelve el dict 'motion' del schema
    en coordenadas de pantalla (px), o None si no es lineal.
    """
    ox, oy = origin_px
    # px en pantalla
    px = [ox + x / TWIPS for x in xs]
    py = [oy + y / TWIPS for y in ys]

    rng_x = max(px) - min(px)
    rng_y = max(py) - min(py)
    if rng_x < 1e-6 and rng_y < 1e-6:
        return None  # estatica

    if rng_x >= rng_y:
        axis = "x"
        moving = px
        fixed = round(sum(py) / len(py), 2)
    else:
        axis = "y"
        moving = py
        fixed = round(sum(px) / len(px), 2)

    vmin = min(moving)
    vmax = max(moving)

    # speed: |delta| modal entre frames consecutivos (ignorando vueltas en los
    # extremos donde el paso puede ser distinto).
    deltas = [abs(moving[i + 1] - moving[i]) for i in range(len(moving) - 1)]
    deltas = [d for d in deltas if d > 1e-6]
    if not deltas:
        return None
    # Mediana es robusta frente a los frames de inflexion en min/max.
    deltas_sorted = sorted(deltas)
    speed = deltas_sorted[len(deltas_sorted) // 2]

    # phase: posicion del frame 0 dentro del ciclo ida-vuelta.
    # 0   -> en min, yendo a max
    # 0.5 -> en max, yendo a min
    start = moving[0]
    nxt = moving[1] if len(moving) > 1 else moving[0]
    going_up = nxt >= start
    span = (vmax - vmin) if (vmax - vmin) > 1e-6 else 1.0
    frac = (start - vmin) / span  # 0..1 a lo largo de min->max
    if going_up:
        phase = 0.5 * frac
    else:
        phase = 1.0 - 0.5 * frac
    # Normalizar a los valores "limpios" tipicos {0.0, 0.5}.
    phase = _snap_phase(phase)

    return {
        "type": "linear_bounce",
        "axis": axis,
        "min": round(vmin, 2),
        "max": round(vmax, 2),
        "fixed": fixed,
        "speed": round(speed, 2),
        "phase": phase,
    }


def _snap_phase(phase: float, tol: float = 0.04) -> float:
    for anchor in (0.0, 0.25, 0.5, 0.75, 1.0):
        if abs(phase - anchor) <= tol:
            return 0.0 if anchor == 1.0 else round(anchor, 3)
    return round(phase, 3)


def extract_ball_trajectories(
    swf_xml: str,
    enemies_sprite_id: int,
    origin_px: Tuple[float, float],
) -> List[dict]:
    """Parsea las matrices PlaceObject2 del sprite `enemies` (enemies_sprite_id),
    recupera la posicion por frame de cada bola y devuelve la lista de balls en
    formato del schema (lista de {"radius":..., "motion": {...}}).

    Reusa el parseo balanceado de subTags.

    Las bolas de un mismo grupo de rebote comparten min/max/speed (mismo
    recorrido y velocidad); solo cambian `fixed` y `phase`. Por eso primero se
    detecta el patron por bola y luego se *consensua* min/max/speed por eje
    usando la mediana entre bolas. Esto evita que una bola cuya fase la hace
    arrancar cerca del extremo (sin muestrear el frame exacto del giro)
    reporte un min/max levemente corto (p.ej. 394 en vez de 395).
    """
    block = extract_sprite_subtags(swf_xml, enemies_sprite_id)
    events = iter_places(block)
    series = _positions_per_depth(events)

    raw: List[dict] = []
    for depth in sorted(series.keys()):
        pts = series[depth]
        if len(pts) < 2:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        motion = _detect_linear_bounce(xs, ys, origin_px)
        if motion is None:
            continue
        raw.append(motion)

    _consensus_geometry(raw)

    balls = [{"radius": BALL_RADIUS, "motion": m} for m in raw]
    # Se mantiene el orden de depth (1,3,5,7 -> filas y descendente), que
    # coincide con el orden de level_01.json.
    return balls


def _median(vals: List[float]) -> float:
    s = sorted(vals)
    n = len(s)
    if n == 0:
        return 0.0
    if n % 2:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2.0


def _consensus_geometry(motions: List[dict]) -> None:
    """Iguala in-place min/max/speed entre las bolas que comparten eje, usando
    el valor mas extremo / la mediana. Asume que las bolas con el mismo eje
    pertenecen al mismo grupo de rebote (cierto en estos niveles)."""
    by_axis: Dict[str, List[dict]] = {}
    for m in motions:
        by_axis.setdefault(m["axis"], []).append(m)
    for axis, group in by_axis.items():
        if len(group) < 2:
            continue
        # El recorrido real va del minimo de los min al maximo de los max:
        # cada bola muestrea al menos uno de los dos extremos con exactitud.
        gmin = min(m["min"] for m in group)
        gmax = max(m["max"] for m in group)
        gspeed = round(_median([m["speed"] for m in group]), 2)
        for m in group:
            m["min"] = round(gmin, 2)
            m["max"] = round(gmax, 2)
            m["speed"] = gspeed


# --------------------------------------------------------------------------- #
# 2) Localizar characterIds e instancias nombradas de un nivel
# --------------------------------------------------------------------------- #


def ratio_for_level(level: int) -> int:
    """Nivel N -> ratio 60 + (N-1)*4 (== frame 61+(N-1)*4 menos 1)."""
    return 60 + (level - 1) * 4


def frame_for_level(level: int) -> int:
    return 61 + (level - 1) * 4


@dataclass
class Instance:
    name: str
    character_id: int
    depth: int
    translate_x: float  # twips
    translate_y: float
    scale_x: float
    scale_y: float


def find_level_instances(swf_xml: str, level: int) -> Dict[str, Instance]:
    """Devuelve {name: Instance} para las instancias nombradas (walls, enemies,
    check1..checkN) del nivel `level`, eligiendo el menor characterId por nombre.

    Se basa en el grupo de PlaceObject2 con ratio == ratio_for_level(level),
    que es como el main timeline marca a que frame/nivel pertenece la instancia.
    """
    target_ratio = ratio_for_level(level)
    # Solo nos interesan los PlaceObject2 con name + characterId + ratio.
    place_re = re.compile(
        r'<item type="PlaceObject2Tag"([^>]*?)(/>|>(.*?)</item>)',
        re.DOTALL,
    )
    out: Dict[str, Instance] = {}
    for m in place_re.finditer(swf_xml):
        attrs = parse_attrs(m.group(1))
        name = attrs.get("name")
        ratio = attrs.get("ratio")
        cid = attrs.get("characterId")
        if name is None or ratio is None or cid is None:
            continue
        if int(ratio) != target_ratio:
            continue
        tx, ty, sx, sy = _matrix_from_inner(m.group(3) or "")
        inst = Instance(
            name=name,
            character_id=int(cid),
            depth=int(attrs.get("depth", "0")),
            translate_x=tx,
            translate_y=ty,
            scale_x=sx,
            scale_y=sy,
        )
        prev = out.get(name)
        if prev is None or inst.character_id < prev.character_id:
            out[name] = inst
    return out


# --------------------------------------------------------------------------- #
# Geometria: shape bounds -> rect en pantalla
# --------------------------------------------------------------------------- #


_SHAPE_BOUNDS_RE = re.compile(
    r'<item type="DefineShape\d*Tag"[^>]*shapeId="{sid}">\s*'
    r'<shapeBounds type="RECT" Xmax="(-?\d+)" Xmin="(-?\d+)" Ymax="(-?\d+)" Ymin="(-?\d+)"'
)


def _shape_bounds(swf_xml: str, shape_id: int) -> Optional[Tuple[float, float, float, float]]:
    """Devuelve (xmin, ymin, xmax, ymax) en twips del DefineShape shape_id."""
    pat = re.compile(
        rf'<item type="DefineShape\d*Tag"[^>]*shapeId="{shape_id}">\s*'
        rf'<shapeBounds type="RECT" ([^/]*)/>'
    )
    m = pat.search(swf_xml)
    if not m:
        return None
    a = parse_attrs(m.group(1))
    return (
        float(a["Xmin"]),
        float(a["Ymin"]),
        float(a["Xmax"]),
        float(a["Ymax"]),
    )


def _sprite_first_child(swf_xml: str, sprite_id: int) -> Optional[Place]:
    """Devuelve el primer PlaceObject2 (con character) dentro del sprite
    sprite_id. Sirve para resolver sprite -> shape interno y su matriz."""
    try:
        block = extract_sprite_subtags(swf_xml, sprite_id)
    except KeyError:
        return None
    for ev in iter_places(block):
        if ev == "SHOWFRAME":
            continue
        p: Place = ev  # type: ignore
        if p.has_char and p.character_id is not None:
            return p
    return None


def checkpoint_rect(swf_xml: str, inst: Instance) -> Optional[dict]:
    """Aproxima el rect de un checkpoint a partir de:
        rect_px = (shape_bounds_twips * escala_sprite * escala_instancia)
                  centrado en la translacion de la instancia.
    El checkpoint suele ser sprite -> shape cuadrado escalado.
    Devuelve {"x","y","w","h"} en px o None si no se pudo resolver.
    """
    child = _sprite_first_child(swf_xml, inst.character_id)
    if child is None or child.character_id is None:
        return None
    bounds = _shape_bounds(swf_xml, child.character_id)
    if bounds is None:
        return None
    xmin, ymin, xmax, ymax = bounds
    # escala total = escala del sprite-child * escala de la instancia
    sx = child.scale_x * inst.scale_x
    sy = child.scale_y * inst.scale_y
    w = (xmax - xmin) * sx / TWIPS
    h = (ymax - ymin) * sy / TWIPS
    cx = inst.translate_x / TWIPS
    cy = inst.translate_y / TWIPS
    return {
        "x": round(cx - w / 2.0, 1),
        "y": round(cy - h / 2.0, 1),
        "w": round(w, 1),
        "h": round(h, 1),
    }


# --------------------------------------------------------------------------- #
# Ensamblado del JSON de nivel
# --------------------------------------------------------------------------- #


def build_level_json(swf_xml: str, level: int) -> dict:
    instances = find_level_instances(swf_xml, level)
    if "enemies" not in instances:
        raise RuntimeError(
            f"No se encontro instancia 'enemies' para nivel {level} "
            f"(ratio {ratio_for_level(level)}). Instancias halladas: "
            f"{sorted(instances)}"
        )

    enemies = instances["enemies"]
    origin_px = (enemies.translate_x / TWIPS, enemies.translate_y / TWIPS)
    balls = extract_ball_trajectories(swf_xml, enemies.character_id, origin_px)

    # Checkpoints en orden check1, check2, check3, check4...
    check_names = sorted(
        [n for n in instances if re.fullmatch(r"check\d+", n)],
        key=lambda n: int(n[5:]),
    )
    checkpoints = []
    play_area = []
    for i, name in enumerate(check_names):
        inst = instances[name]
        rect = checkpoint_rect(swf_xml, inst) or {
            "x": round(inst.translate_x / TWIPS, 1),
            "y": round(inst.translate_y / TWIPS, 1),
            "w": 0,
            "h": 0,
            "_todo": "geometria del checkpoint no resuelta; medir PNG",
        }
        cp = {"id": name, "rect": {k: rect[k] for k in ("x", "y", "w", "h")}}
        if i == 0:
            cp["is_spawn"] = True
            cp["respawn"] = {
                "x": round(inst.translate_x / TWIPS, 1),
                "y": round(inst.translate_y / TWIPS, 1),
            }
        if i == len(check_names) - 1:
            cp["is_goal"] = True
        checkpoints.append(cp)
        play_area.append(dict(cp["rect"]))

    spawn = {"x": 0, "y": 0}
    if checkpoints:
        spawn = dict(checkpoints[0].get("respawn", {"x": 0, "y": 0}))

    walls_inst = instances.get("walls")
    walls_todo = []
    if walls_inst is not None:
        # La geometria de las paredes es un shape vectorial complejo (corredor).
        # No la aproximamos a rects automaticamente aqui: dejamos un TODO con la
        # info necesaria para refinarla midiendo el PNG del frame.
        walls_todo.append(
            {
                "_todo": (
                    "Geometria fina de paredes/corredor pendiente. "
                    f"characterId={walls_inst.character_id}, "
                    f"placed at ({walls_inst.translate_x/TWIPS:.1f},"
                    f"{walls_inst.translate_y/TWIPS:.1f}) px. "
                    f"Refinar midiendo decompiled/frames/{frame_for_level(level)}.png "
                    "o trazando el DefineShape correspondiente."
                )
            }
        )

    level_json = {
        "name": f"Level {level}",
        "level_index": level,
        "area": dict(AREA),
        "player": {
            "size": PLAYER_SIZE,
            "speed": PLAYER_SPEED,
            "spawn": spawn,
        },
        "coins_required": 0,
        "play_area": play_area,
        "walls": walls_todo,
        "checkpoints": checkpoints,
        "coins": [],
        "balls": balls,
        "source": {
            "swf_frame": frame_for_level(level),
            "swf_ratio": ratio_for_level(level),
            "enemies_sprite": enemies.character_id,
            "enemies_origin_px": [round(origin_px[0], 2), round(origin_px[1], 2)],
            "ball_period_frames": _sprite_frame_count(swf_xml, enemies.character_id),
            "notes": (
                "Trayectorias de bolas extraidas automaticamente de las matrices "
                "PlaceObject del clip 'enemies' (extract_level.py). Geometria de "
                "checkpoints aproximada desde shape bounds * escala; "
                "walls/play_area pueden refinarse midiendo el PNG del frame."
            ),
        },
    }
    return level_json


def _sprite_frame_count(swf_xml: str, sprite_id: int) -> Optional[int]:
    m = re.search(
        rf'<item type="DefineSpriteTag"[^>]*frameCount="(\d+)"[^>]*spriteId="{sprite_id}"',
        swf_xml,
    )
    if m:
        return int(m.group(1))
    return None


# --------------------------------------------------------------------------- #
# Verificacion contra level_01.json
# --------------------------------------------------------------------------- #


def verify_balls(generated: dict, reference_path: str,
                 tol_px: float = 0.5, tol_phase: float = 0.02) -> Tuple[bool, str]:
    with open(reference_path, "r", encoding="utf-8") as fh:
        ref = json.load(fh)
    gen_balls = generated["balls"]
    ref_balls = ref["balls"]
    lines = []
    ok = True
    if len(gen_balls) != len(ref_balls):
        ok = False
        lines.append(
            f"  numero de bolas: generado={len(gen_balls)} ref={len(ref_balls)}"
        )

    # Emparejar greedy por (fixed) ya que cada fila tiene fixed distinto.
    def key(b):
        m = b["motion"]
        return (m["axis"], m["fixed"])

    ref_sorted = sorted(ref_balls, key=key)
    gen_sorted = sorted(gen_balls, key=key)
    n = min(len(ref_sorted), len(gen_sorted))
    for i in range(n):
        g = gen_sorted[i]["motion"]
        r = ref_sorted[i]["motion"]
        diffs = {
            "axis": (g["axis"], r["axis"], g["axis"] == r["axis"]),
            "min": (g["min"], r["min"], abs(g["min"] - r["min"]) <= tol_px),
            "max": (g["max"], r["max"], abs(g["max"] - r["max"]) <= tol_px),
            "fixed": (g["fixed"], r["fixed"], abs(g["fixed"] - r["fixed"]) <= tol_px),
            "speed": (g["speed"], r["speed"], abs(g["speed"] - r["speed"]) <= tol_px),
            "phase": (g["phase"], r["phase"], abs(g["phase"] - r["phase"]) <= tol_phase),
        }
        row_ok = all(v[2] for v in diffs.values())
        ok = ok and row_ok
        status = "OK " if row_ok else "FAIL"
        detail = ", ".join(
            f"{k}={v[0]}~{v[1]}" + ("" if v[2] else " <X>")
            for k, v in diffs.items()
        )
        lines.append(f"  [{status}] bola {i+1}: {detail}")

    verdict = "PASS" if ok else "FAIL"
    header = (
        f"Verificacion bolas vs {os.path.basename(reference_path)} "
        f"(tol {tol_px}px / {tol_phase} fase): {verdict}"
    )
    return ok, header + "\n" + "\n".join(lines)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Extractor de niveles WHG desde swf.xml")
    ap.add_argument("--level", type=int, required=True, help="Numero de nivel (1..30)")
    ap.add_argument("--out", type=str, default=None, help="Ruta del JSON de salida")
    ap.add_argument("--swf-xml", type=str, default=DEFAULT_SWF_XML, help="Ruta a swf.xml")
    ap.add_argument(
        "--verify",
        action="store_true",
        help="Compara las bolas con src/levels/level_01.json (solo nivel 1)",
    )
    ap.add_argument(
        "--print",
        dest="do_print",
        action="store_true",
        help="Imprime el JSON por stdout en vez de (o ademas de) escribirlo",
    )
    args = ap.parse_args(argv)

    swf_xml = read_text(args.swf_xml)
    level_json = build_level_json(swf_xml, args.level)
    text = json.dumps(level_json, indent=2, ensure_ascii=False)

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(f"Escrito: {args.out}  ({len(level_json['balls'])} bolas, "
              f"{len(level_json['checkpoints'])} checkpoints)")

    if args.do_print or not args.out:
        print(text)

    rc = 0
    if args.verify:
        ref = os.path.join(DEFAULT_LEVELS_DIR, f"level_{args.level:02d}.json")
        if not os.path.exists(ref):
            print(f"[verify] no existe referencia {ref}", file=sys.stderr)
            rc = 2
        else:
            ok, report = verify_balls(level_json, ref)
            print(report)
            rc = 0 if ok else 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
