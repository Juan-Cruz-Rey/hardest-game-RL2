# extract_level.py — Extractor de niveles WHG

Genera los JSON data-driven (`src/levels/level_NN.json`, ver `src/levels/schema.md`)
a partir del dump XML del SWF decompilado (`decompiled/swf.xml`).

## Uso

```bash
# Escribir un nivel a disco
python tools/extract_level.py --level 1 --out src/levels/level_01.json

# Imprimir por stdout sin escribir
python tools/extract_level.py --level 3 --print

# Verificar que las bolas coinciden con la referencia hecha a mano (nivel 1)
python tools/extract_level.py --level 1 --verify
```

Solo stdlib (sin numpy/PIL). XML de enterada configurable con `--swf-xml`.

## Como funciona

- **Mapeo nivel -> frame/ratio.** Nivel N usa el grupo de `PlaceObject2` con
  `ratio == 60 + (N-1)*4` (== `frame 61+(N-1)*4`, el ratio es frame-1).
  De ahi salen las instancias nombradas `walls`, `enemies`, `check1..checkN`
  con su `characterId` (menor id por nombre) y su matriz de colocacion.
- **Bolas.** `extract_ball_trajectories(swf_xml, enemies_sprite_id, origin_px)`
  abre el `DefineSpriteTag` del clip `enemies` (parseo balanceado de `<subTags>`),
  simula el display list frame a frame para reconstruir la posicion por-frame
  de cada depth, y detecta el patron `linear_bounce` (axis/min/max/fixed/speed/phase)
  en px de pantalla. Las bolas de un grupo comparten min/max/speed: se consensuan
  para evitar que una fase desfasada reporte un extremo corto.
- **Checkpoints.** Rect ~= bounds del shape interno * escala (sprite * instancia),
  centrado en la translacion de la instancia.

## Verificacion (nivel 1)

`--verify` compara contra `src/levels/level_01.json` con tolerancia 0.5px / 0.02 fase.
Resultado: **PASS** en las 4 bolas (axis x, min 156, max 395, fixed {238,213,188,163},
speed 6.65~6.64, fases {0,0.5,0,0.5}).

## Limitaciones conocidas

1. **Solo `linear_bounce` directo.** El extractor reconstruye bolas cuyo tween
   vive directamente en el clip `enemies` con traslacion en un eje (nivel 1).
   Otros niveles usan variantes que aun NO se decodifican y dan `balls: []`:
   - **Nivel 2** (sprite 181): 12 instancias de un sub-clip (char 180) que tweenea
     internamente en Y. Hay que resolver el tween del sub-clip y sumarlo al offset
     de cada instancia.
   - **Nivel 5** (sprite 212): 1 bola con un path de 128 frames (no es rebote en un
     eje; seguramente `circular`/`path`).
   Extender: detectar tweens en sub-clips y agregar tipos `circular`/`path`/`static`.
2. **Geometria de `walls`/`play_area` aproximada.** `walls` queda como TODO con el
   `characterId` y la posicion; `play_area` se rellena solo con los rects de los
   checkpoints. El corredor real es un shape vectorial: refinar midiendo el PNG
   `decompiled/frames/{frame}.png` o trazando el `DefineShape`.
3. **Checkpoints** asume shape cuadrado escalado; rect es aproximado (p.ej. nivel 1
   da 50,125,75,150 vs el afinado a mano 52,127,72,145). Suficiente para empezar.
4. `coins`, `coins_required` y respawns por-checkpoint no se extraen aun (quedan
   en sus valores por defecto).
