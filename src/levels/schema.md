# Formato de nivel JSON — The World's Hardest Game (Python/Pygame)

Cada nivel se describe **100% por data**. El motor (`engine.py`) no contiene nada hardcodeado de
ningún nivel: lee este JSON y lo simula. El sistema de coordenadas es **el mismo del SWF original**:
origen `(0,0)` arriba-izquierda, `x` hacia la derecha, `y` hacia abajo, unidades en píxeles.
El área jugable interna del original es 550×400 (con barras negras de UI arriba/abajo que NO son
parte de la simulación; el área de juego efectiva empieza debajo de la barra superior).

## Esquema (campos)

```jsonc
{
  "name": "Level 1",                // etiqueta legible
  "level_index": 1,                 // 1..30 (número de nivel del original)

  "area": {                         // dimensiones del lienzo de simulación
    "width": 550,
    "height": 400
  },

  "player": {
    "size": 12,                     // lado del cuadrado rojo en px (centro = posición)
    "speed": 3.0,                   // px por step de física (= _root.speed del original)
    "spawn": { "x": 87, "y": 200 }  // posición inicial = check1 (centro del cuadrado)
  },

  "coins_required": 0,              // monedas a juntar antes de poder ganar (coins[level-1])

  // Geometría estática. Todo en rects axis-aligned (el original es pixel-perfect sobre
  // shapes vectoriales; los aproximamos con la unión de rects equivalente).
  "walls": [                        // zonas SÓLIDAS: el jugador no puede entrar.
    { "x": 0, "y": 0, "w": 550, "h": 10 }   // x,y = esquina sup-izq; w,h = tamaño
    // El motor también trata como pared TODO lo que esté fuera del área jugable
    // definida por `play_area` (ver abajo), de modo que las paredes pueden expresarse
    // como el "marco" alrededor del corredor.
  ],

  "play_area": [                    // (opcional) rects donde el jugador SÍ puede estar.
    { "x": 52, "y": 127, "w": 445, "h": 145 }
    // Si está presente, el jugador muere/queda bloqueado fuera de la unión de estos rects.
    // Modela el corredor + las dos cámaras verdes. Alternativa equivalente a `walls`:
    // un nivel puede definirse con `walls` (negativo) o `play_area` (positivo) o ambos.
  ],

  "checkpoints": [                  // zonas verdes. La primera (is_spawn) es el respawn inicial.
    {
      "id": "check1",
      "rect": { "x": 52, "y": 127, "w": 72, "h": 145 },
      "is_spawn": true,             // donde aparece el jugador al empezar
      "respawn": { "x": 87, "y": 200 }  // punto exacto de reaparición al tocar este checkpoint
    },
    {
      "id": "check2",
      "rect": { "x": 425, "y": 127, "w": 72, "h": 145 },
      "is_goal": true               // tocar esto (con coins_required juntadas) = victoria
    }
  ],

  "coins": [                        // coleccionables (amarillos). Vacío en nivel 1.
    // { "x": 250, "y": 200, "r": 6 }
  ],

  // Bolas azules. En el original son motion tweens de timeline; los portamos a un patrón
  // paramétrico que el motor interpreta. Patrón principal: rebote lineal.
  "balls": [
    {
      "radius": 8,                  // radio del círculo azul en px
      "motion": {
        "type": "linear_bounce",    // ida y vuelta entre min..max sobre un eje
        "axis": "x",                // "x" (horizontal) o "y" (vertical)
        "min": 156,                 // extremo inferior del recorrido (px, centro de la bola)
        "max": 395,                 // extremo superior
        "fixed": 163,               // coordenada constante en el otro eje (si axis="x", es la y)
        "speed": 6.64,              // px por step de física (velocidad del tween)
        "phase": 0.0                // 0..1: posición inicial dentro del ciclo de ida-vuelta.
                                    // 0 = en `min` yendo hacia `max`; 0.5 = en `max` yendo a `min`.
      }
    }
  ],

  // Metadatos de procedencia (de dónde salió la data). No lo usa el motor.
  "source": {
    "swf_frame": 61,
    "enemies_sprite": 150,
    "ball_period_frames": 72,
    "notes": "Trayectorias extraídas de las matrices PlaceObject del swf2xml."
  }
}
```

## Notas de diseño

- **Data-driven puro**: el motor recibe la ruta a un JSON y reconstruye el nivel. Nada del nivel 1
  vive en el código.
- **Colisión**: el original usa `hitTest` pixel-perfect. Lo replicamos con geometría:
  - Paredes: AABB cuadrado-rojo vs rects sólidos; al chocar se cancela el movimiento en ese eje
    (igual que el original, que deshace el paso eje por eje).
  - Bolas: distancia círculo–círculo (se aproxima el cuadrado del jugador por su círculo
    inscrito/su AABB; usamos AABB-vs-círculo para fidelidad).
  - Checkpoint/meta: solापamiento AABB.
- **Patrones de movimiento extensibles**: `type` permite agregar `circular`, `path` (lista de
  puntos), `static`, etc. para los 29 niveles restantes sin tocar el contrato existente.
- **Separación sim/render**: estos campos solo describen el estado; el render se deriva de ellos.

## Mapa de extracción (frame del SWF ↔ nivel)

Nivel N → `frame_{61 + (N-1)*4}` del timeline principal. Cada nivel define instancias
nombradas `walls`, `enemies`, `check1`, `check2` (a veces `check3`) con un `characterId` propio.
El de menor id corresponde al nivel. Las trayectorias de bolas salen de las matrices
`PlaceObject2` del clip `enemies` (un tween por bola, periodo = frameCount del clip).
