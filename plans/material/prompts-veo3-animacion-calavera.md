# Prompts — animar las poses base con Veo 3 (image-to-video)

Continúa `plans/material/prompts-sprites-calavera.md` — usa como imagen de
entrada (I2V) cada una de las 4 poses base ya generadas ahí (`inactivo`,
`escuchando`, `hablando`, `procesando`).

## Aviso antes de generar: Veo 3 va a pelear contra la regla de bordes duros

Veo 3 está entrenado para movimiento cinematográfico/fotorrealista —
iluminación que respira, micro-shake de cámara, gradientes sutiles. Todo
eso es exactamente lo que **no** puede tener este sprite (transparencia por
color clave = binaria, un gradiente en el fondo magenta rompe el recorte
limpio en cada cuadro, no solo en uno). No esperar un video perfecto en el
primer intento — el flujo real es: generar, extraer cuadros, umbralizar a
blanco/negro puro (mismo paso que ya usaba `convertir_ascii.py` en su
primer paso, "pasar a gris" — acá se corta a blanco/negro puro en vez de
mapear a caracteres), y si el fondo no quedó magenta parejo, reemplazarlo
por color clave exacto con tolerancia. Ver el paso a paso completo al final
de este documento.

## Reglas comunes a los 4 prompts

- **Bloqueo de identidad — la más importante, la que faltaba.** I2V no
  garantiza que el personaje se mantenga igual, solo que arranca de esa
  imagen — el modelo puede "redibujar" proporciones, forma de los ojos,
  grosor del trazo cuadro a cuadro. Hay que pedirlo explícito y repetirlo:
  `preserve the exact same character design throughout, same skull shape,
  same eye socket shape and size, same proportions, same line thickness,
  do not redesign the character, do not add or remove details, only animate
  the described motion, character must look identical to the input image in
  every frame except for the described movement`. Si la herramienta expone
  un control de "fidelidad a la imagen de referencia" / "creativity" /
  "motion strength", bajarlo al mínimo que todavía anime algo — cuanta más
  libertad creativa, más deriva de diseño.
- **Cámara fija, sin excepción.** Sin esto Veo 3 por defecto puede meter un
  paneo/zoom sutil (`Veo 3 defaults to static or subtle handheld motion`
  si no se especifica lo contrario — hay que especificarlo). Se pide
  explícito: `locked static camera, no camera movement, no pan, no zoom,
  no dolly, tripod shot`.
- **Loop.** Se pide que el primer y último cuadro coincidan
  (`seamless looping motion, first and last frame match exactly`) — así el
  GIF final no salta al reiniciar el bucle.
- **Nada de iluminación/sombra/color nuevo.** Hay que repetirlo aunque ya
  esté en la imagen de entrada, porque el modelo de video tiende a "mejorar"
  la escena con luz ambiente si no se lo prohíbe explícito.
- **Sin audio.** Veo 3 genera audio por defecto — no hace falta acá,
  se descarta en el post-proceso igual, pero pedir `no audio, silent` evita
  que el modelo gaste generación en un sonido que se va a tirar.
- **Duración corta.** Pedir el mínimo que la herramienta permita (Veo 3
  suele generar clips de ~8s) — sobra de lejos para 1-2 ciclos de loop; el
  resto se descarta al recortar a los 8-12 cuadros finales del GIF.

---

## 1. `inactivo` — parpadeo lento, respiración sutil

Imagen de entrada: pose base "inactivo".

```
Animate this skull character with locked static camera, no camera
movement, no pan, no zoom, no dolly, tripod shot. Preserve the exact same
character design throughout, same skull shape, same eye socket shape and
size, same proportions, same line thickness, do not redesign the
character, do not add or remove details, character must look identical to
the input image in every frame except for the described movement. Subtle
idle breathing motion: the skull very slightly rises and falls in place,
one eye blinks slowly once during the clip, no other movement. Keep the
exact same flat black and white comic ink art style, hard sharp edges, no
anti-aliasing, no blur, no added shadows, no gradients, no new lighting,
background stays solid flat magenta with zero variation throughout.
Seamless looping motion, first and last frame match exactly. No audio,
silent, no camera shake.
```

## 2. `escuchando` — inclinación leve, atención

Imagen de entrada: pose base "escuchando".

```
Animate this skull character with locked static camera, no camera
movement, no pan, no zoom, no dolly, tripod shot. Preserve the exact same
character design throughout, same skull shape, same eye socket shape and
size, same proportions, same line thickness, do not redesign the
character, do not add or remove details, character must look identical to
the input image in every frame except for the described movement. Subtle
attentive motion: the skull leans very slightly further forward and back
in a tiny repeating motion, ear spikes twitch slightly once, eyes stay
wide open and alert throughout, no other movement. Keep the exact same
flat black and white comic ink art style, hard sharp edges, no
anti-aliasing, no blur, no added shadows, no gradients, no new lighting,
background stays solid flat magenta with zero variation throughout.
Seamless looping motion, first and last frame match exactly. No audio,
silent, no camera shake.
```

## 3. `hablando` — mandíbula abriendo y cerrando

Imagen de entrada: pose base "hablando".

```
Animate this skull character with locked static camera, no camera
movement, no pan, no zoom, no dolly, tripod shot. Preserve the exact same
character design throughout, same skull shape, same eye socket shape and
size, same proportions, same line thickness, do not redesign the
character, do not add or remove details, character must look identical to
the input image in every frame except for the described movement. The jaw
opens and closes repeatedly as if talking, rhythmic and continuous, rest
of the skull stays completely still, no head movement, no body movement.
Keep the exact same flat black and white comic ink art style, hard sharp
edges, no anti-aliasing, no blur, no added shadows, no gradients, no new
lighting, background stays solid flat magenta with zero variation
throughout. Seamless looping motion, first and last frame match exactly.
No audio, silent, no camera shake.
```

## 4. `procesando` — signo de interrogación flotando

Imagen de entrada: pose base "procesando". Nota: el resultado real del
prompt de generación de imagen trajo un signo de interrogación flotando
sobre la cabeza en vez del engranaje/swirl pedido originalmente — el
prompt de animación de abajo se ajustó para describir LO QUE LA IMAGEN
REALMENTE TIENE, no lo que se pidió al generarla. **Regla general para
cualquier estado: siempre describir el símbolo/detalle tal como aparece en
la imagen final, no como se lo pidió — si no coinciden, Veo 3 intenta
"corregir" la imagen para que matchee el prompt, y eso es exactamente el
redibujo que rompe la identidad del personaje.**

```
Animate this skull character with locked static camera, no camera
movement, no pan, no zoom, no dolly, tripod shot. Preserve the exact same
character design throughout, same skull shape, same eye socket shape and
size, same proportions, same line thickness, do not redesign the
character, do not add or remove details, character must look identical to
the input image in every frame except for the described movement. The
question mark symbol floating above the head bobs gently up and down in a
slow continuous loop, the skull body stays completely still, no head
movement. Keep the exact same flat black and white comic ink art style,
hard sharp edges, no anti-aliasing, no blur, no added shadows, no
gradients, no new lighting, background stays solid flat magenta with zero
variation throughout. Seamless looping motion, first and last frame match
exactly. No audio, silent, no camera shake.
```

---

## Post-proceso obligatorio (los 4 clips van a necesitarlo)

1. Extraer cuadros del mp4 (cualquier herramienta de video, o `ffmpeg -i
   clip.mp4 frame_%03d.png`).
2. Quedarse con 8-12 cuadros por loop (según el fps por estado ya definido
   en `plans/INVESTIGACION-2026-07-27-voz-tools-ui.md` sección 13.6:
   `inactivo` 8fps, `escuchando` 10fps, `hablando` 12fps, `procesando`
   12fps) — no hace falta usar todos los cuadros que salieron del video,
   se puede tomar 1 de cada N.
3. Umbralizar cada cuadro a blanco/negro puro (sin grises intermedios) —
   mata de un golpe cualquier gradiente o sombra que Veo 3 haya metido.
4. Confirmar que el fondo quedó en el color clave exacto (`#FF00FE`); si
   no, reemplazar por color exacto con tolerancia baja.
5. Recortar a 200×200px, exportar como GIF animado (ver formato en la
   sección 13.6 de la investigación).
6. Comparar el primer y último cuadro a ojo — si no calzan bien pese al
   prompt de loop, duplicar/recortar cuadros a mano hasta que el ciclo no
   salte.
