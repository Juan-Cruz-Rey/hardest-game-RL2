# The World's Hardest Game — reimplementación en Python

Reimplementación fiel de *The World's Hardest Game* (Snubby Land) en Python + Pygame,
a partir del SWF original decompilado, pensada como base para entrenar un agente de
**Reinforcement Learning** sobre el juego.

El objetivo es recrear los 30 niveles de forma **data-driven** (cada nivel es un JSON) y
con una simulación **separada del render**, de modo que la física pueda correr sin
ventana (headless) para RL.

> Estado actual: **Nivel 1 completo y validado** contra el original (física fiel al
> ActionScript y render ~96% píxel-idéntico). Los otros 29 niveles aún no.

---

## Estructura

```
src/                  El juego (esto es lo que se ejecuta)
  play.py             Punto de entrada jugable (flechas/WASD)
  engine.py           Simulación PURA, sin pygame (corre headless → lista para RL)
  render.py           Render con pygame (solo LEE el estado del engine)
  level.py            Carga y modelo de datos de un nivel (dataclasses)
  levels/
    schema.md         Esquema del formato JSON de nivel, documentado
    level_01.json     Datos exactos del nivel 1 (geometría, bolas, checkpoints)

tests/                Suite de tests (pytest) de la simulación
scripts/              Utilidades de extracción/validación desde el SWF
  extract_level.py    Extractor reutilizable SWF → JSON (formato del schema)
  capture_level.py    Renderiza un nivel a PNG (headless) para comparar
  compare_balls.py    Compara posiciones de bolas port vs original

tools/                (ignorado) JPEXS ffdec descargado para decompilar el SWF
decompiled/           (ignorado) salida de la decompilación del SWF
flash/                SWF original
```

`src/` es el juego; nada del nivel 1 está hardcodeado en el código — todo sale del JSON.

---

## Requisitos

- Python 3.10+
- `pygame`, `numpy` (render y utilidades)
- `pytest` (tests)
- Para volver a decompilar: Java 8+ y [JPEXS ffdec](https://github.com/jindrapetrik/jpexs-decompiler)

```bash
pip install pygame numpy pytest
```

---

## Cómo jugar

```bash
cd src
python play.py --scale 1.4
```

Controles: **flechas o WASD** mover · **R** reiniciar · **Esc** salir.

Opciones:
- `--scale N` escala la ventana (el nivel es 550×400 nativo).
- `--sim-hz N` ticks de simulación por segundo (default **30**, el tick del SWF original).
- `--fps N` fps de render (la física sigue corriendo a `--sim-hz`).

> **Importante:** el SWF original corre a **30 fps** y la velocidad de bolas/jugador está
> calibrada por frame. La simulación usa *fixed timestep* a 30 Hz, desacoplado del render,
> para reproducir la velocidad exacta del original sin importar el framerate de la pantalla.

---

## Cómo está modelado el nivel (data-driven)

Cada nivel se describe en un JSON (ver `src/levels/schema.md`):
área, jugador (tamaño, velocidad, spawn), checkpoints (inicio/meta), paredes / zona
jugable, monedas y **bolas** con su patrón de movimiento.

En el original las bolas se mueven por *motion tweens* de la línea de tiempo (no por código);
acá se portan a un patrón paramétrico que el motor interpreta. El nivel 1 usa
`linear_bounce` (rebote lineal entre dos extremos sobre un eje):

```json
{ "type": "linear_bounce", "axis": "x", "min": 156, "max": 395,
  "fixed": 238, "speed": 6.64, "phase": 0.0 }
```

Las trayectorias del nivel 1 se extrajeron **exactas** de las matrices `PlaceObject` del
SWF; la geometría (corredor con sus muescas, zonas verdes) se midió píxel a píxel del
render original.

---

## Fidelidad al original (nivel 1)

La simulación replica el `enterFrame` del ActionScript original:

- Movimiento del cuadrado rojo a `speed` px/tick (ejes independientes).
- Colisión con paredes / confinamiento a la zona jugable (corredor con muescas).
- Muerte al tocar una bola: animación de *fade* de **25 ticks** y luego respawn en el
  último checkpoint (la muerte **no** es instantánea, igual que el original).
- Detección de muerte por 5 puntos (centro + 4 medios de los lados), como el original.
- Victoria al tocar la meta con las monedas requeridas (0 en el nivel 1).

Validación visual: render **~96% píxel-idéntico** al frame original (el resto es
anti-aliasing de rasterización entre el SWF y pygame).

---

## Tests

```bash
python -m pytest tests -q
```

Cubren física de bolas (posiciones, periodo, fases), confinamiento del jugador, muerte y
respawn, victoria, determinismo y una corrida headless.

---

## RL (próximo paso, aún no implementado)

`engine.py` ya está pensado para esto: corre sin pygame, es determinista, expone
`reset()`, `step(action)`, `state_vector()` y un espacio de acciones discreto (`ACTIONS`).
El siguiente paso es envolverlo en una interfaz tipo Gymnasium (`reset`/`step`/`render`).

> Nota: se descartó entrenar RL directamente sobre el SWF en Flash — el runtime está
> discontinuado, no expone API de control ni estado, no es determinista ni paralelizable,
> y no se puede acelerar el tiempo. El motor Python headless es la base correcta.

---

## Reproducir la decompilación (opcional)

El `decompiled/` y `tools/` no se versionan. Para regenerarlos desde el SWF:

```bash
# con JPEXS ffdec (ffdec.jar) y Java instalados
java -jar tools/ffdec/ffdec.jar -export script decompiled flash/the-world's-hardest-game.swf
java -jar tools/ffdec/ffdec.jar -swf2xml flash/the-world's-hardest-game.swf decompiled/swf.xml
java -jar tools/ffdec/ffdec.jar -export frame decompiled/frames flash/the-world's-hardest-game.swf
```
