# Fase 09 — Panel central con animación ASCII reactiva

## Objetivo

Reemplazar el texto de estado simple del panel central (dejado como
placeholder en la Fase 08) por una animación en arte ASCII, reactiva al
estado real del asistente (inactivo / escuchando / hablando / procesando),
respetando la estética blanco-sobre-negro definida en la Fase 08.

## Contexto

Depende de las **Fases 06 y 08** (necesita saber el estado real de
`VoiceEngine` para reaccionar, y necesita el shell visual/CSS ya montado).
El usuario definió el estilo deseado en la conversación de diseño:
"arte ASCII animado", coherente con la misma estética Watch Dogs 2
(monocromático, trazo blanco, con UNA sola excepción de color — ver abajo).

**El usuario ya entregó material real** para esta fase, ANTES de que se
ejecutara: una ilustración ASCII de una calavera generada con una
herramienta externa (componente React/Next.js, no reutilizable tal cual
en este proyecto porque acá el frontend es HTML/CSS/JS plano vía
pywebview, Fase 08). Ese material vive en:

- `plans/material/skull-illustration-source.tsx` — fuente original tal
  cual la entregó el usuario, JSX/React, **solo de referencia, no se
  importa ni se ejecuta como React en ningún lado**.
- `plans/material/ascii_skull.json` — datos limpios extraídos de ese
  archivo (charset, parámetros de tipografía, color de texto corregido,
  efecto glitch) más la instrucción exacta (regex + `JSON.parse` para
  des-escapar los `\n`) para extraer el string completo del frame desde
  el `.tsx` — el string en sí no se duplicó a mano en el JSON para no
  arriesgar corromper miles de caracteres de arte ASCII.

Detalles importantes de ese material, ya confirmados con el usuario
(no volver a preguntar esto):

- Es **UN solo frame estático** (el array `FRAMES` del original tiene
  longitud 1) — no es una animación cuadro-a-cuadro real, es una
  ilustración fija con un efecto CSS de glitch encima.
- Charset de brillo usado: `" .:░▒▓█"` (más disperso a más denso).
- Tipografía: `'Fira Code'` con fallback a la pila monoespaciada del
  proyecto, tamaño 24px, `letter-spacing: -0.14px`, `line-height: 1`.
- Color de texto: el original traía negro (`#000000`) sobre fondo
  transparente — bug del original, invisible sobre el fondo negro de
  este proyecto. **Corregido a blanco** (`--text: #f5f5f5`, la variable
  ya definida en la guía visual de Fase 08).
- Efecto glitch: aberración cromática roja/azul
  (`text-shadow: 2px 0 0 red, -2px 0 0 blue`) — el usuario confirmó
  explícitamente que se ve mejor así, y esto queda documentado como la
  **única excepción de color de toda la interfaz** (ver nota agregada en
  `plans/phase-08-interfaz-base.md`, sección "Guía visual"). No
  convertirlo a blanco/negro, no quitarlo.
- Comportamiento de escala: el componente original mide el ancho
  disponible del contenedor contra el ancho natural del `<pre>` y aplica
  `transform: scale(...)` si no entra — replicar ese mismo comportamiento
  en la versión vanilla JS (usar `ResizeObserver`, igual que el original).

## Alcance de esta fase

### 0. Portar el material entregado a vanilla JS (arte base, estado "inactivo")

En `Jarvis/assets/app.js`, escribir una función de render (sin React,
sin JSX) que reproduzca el mismo resultado visual que
`skull-illustration-source.tsx`:

- Cargar el frame (extraído de `plans/material/ascii_skull.json` /
  `skull-illustration-source.tsx` según la instrucción de extracción ya
  documentada ahí) dentro de un `<pre>` con la tipografía y color
  definidos arriba.
- Aplicar el `text-shadow` rojo/azul del glitch.
- Replicar el auto-escalado por `ResizeObserver` del original.
- Esto se convierte en el arte del estado **"inactivo"** — es la base
  visual por defecto del panel central.

### 1. Modo A — Convertir un video/gif adicional del usuario (opcional, a futuro)

Crear script standalone `Jarvis/tools/convertir_ascii.py` (herramienta de
desarrollo, no se ejecuta en runtime de la app):

```python
"""
Uso: python convertir_ascii.py entrada.mp4 salida.json --cols 100 --fps 12

Lee el video/gif de entrada, extrae frames a `fps` cuadros por segundo,
convierte cada frame a una grilla de texto de `cols` columnas de ancho
(alto proporcional manteniendo aspect ratio, corregido por el factor de
~0.55 de aspecto de caracteres monoespaciados), usando una rampa de
caracteres por brillo: " .:-=+*#%@" (de más oscuro/vacío a más denso).
Guarda la lista de frames (cada uno un array de strings, una por fila) en
un JSON: {"fps": 12, "frames": [[...], [...], ...]}.
"""
```

Dependencias: `opencv-python` (o `Pillow` + lectura de frames de gif si la
fuente es gif) — agregar la que corresponda a `requirements.txt` SOLO si
el usuario efectivamente entrega un archivo para convertir (si no se usa
el Modo A, no hace falta instalarla).

El JSON resultante se guarda en `Jarvis/assets/ascii_frames.json` y el
frontend (`app.js`) lo reproduce en loop dibujando cada frame dentro de un
`<pre>` a intervalos de `1000/fps` ms.

### 2. Variantes de estado sobre el mismo arte base (escuchando/hablando/procesando)

Como el material entregado (sección 0) es un único frame estático, los
otros 3 estados NO se resuelven con frames nuevos — se resuelven
modulando programáticamente ese mismo frame en `app.js`:

- **Inactivo**: el frame tal cual, glitch sutil y poco frecuente (el
  `.glitch` de transición de la Fase 08, disparado ocasionalmente cada
  varios segundos, no en loop).
- **Escuchando**: aumentar la frecuencia del glitch (dispara más seguido,
  ej. cada 1-2s en vez de cada 5-8s) y/o intensificar levemente el offset
  del `text-shadow` rojo/azul mientras dura el estado.
- **Hablando**: además de lo anterior, aplicar un reemplazo aleatorio
  liviano de un pequeño porcentaje de caracteres del frame por otros de
  `charset` (`" .:░▒▓█"`) en cada intervalo corto (ej. cada 100-150ms,
  swapear 1-3% de los caracteres no-espacio) — da sensación de
  "vibración"/ruido de señal mientras responde, sin necesitar frames
  nuevos.
- **Procesando**: variante intermedia entre inactivo y escuchando (glitch
  a frecuencia media), o un patrón de "barrido" simple (ej. una franja de
  intensidad de glitch que recorre el frame de arriba a abajo en loop) —
  a elección de quien implemente, no hace falta que sea muy elaborado.

Si en el futuro el usuario entrega más material (otro frame, u otro
video/gif vía el Modo A de la sección 1), estas mismas 4 variantes deben
seguir funcionando sobre el material nuevo sin reescribir la lógica de
reactividad — separar claramente "qué arte se muestra" de "cómo se
modula según el estado".

### 3. Reactividad al estado

El frontend debe conocer el estado actual del asistente en tiempo real.
Mecanismo: el backend (`Jarvis/app/server.py`, Fase 08) expone un
endpoint `GET /api/estado` (polling simple cada ~500ms desde `app.js`, no
hace falta websocket para esto) que devuelve
`{"estado": "inactivo"|"escuchando"|"hablando"|"procesando"}`, leyendo el
estado real de `VoiceEngine` (Fase 06) y de `GeminiAgent` (Fase 05,
mientras está resolviendo una llamada).

Cuando el estado cambia, aplicar la clase `.glitch` (definida en la guía
visual de la Fase 08) al panel por 200–300ms como transición, y luego
asentar en el patrón/velocidad correspondiente al nuevo estado.

### 4. Texto de estado + caption

Mantener (no quitar) un texto de estado corto superpuesto (ej. esquina del
panel, no tapando el centro de la animación) y un área de "caption" debajo
mostrando la última frase reconocida/respondida — igual función que tenía
el HRZ (`jhrz-estado`, `jhrz-caption-text`, ver referencia visual revisada
en el diseño), pero con la tipografía y colores monocromáticos definidos
en la Fase 08, no los cyan del original.

## Fuera de alcance

- No implementar todavía la ventana flotante PIP (Fase 10) — esta fase es
  solo el panel dentro de la ventana principal.
- No hace falta construir ni usar el Modo A (conversión de video/gif
  nuevo) en esta fase — el material base ya está resuelto por la sección
  0. El script `convertir_ascii.py` se deja listo para el futuro, pero no
  es un requisito de esta fase tener otro archivo convertido.
- No reimplementar el componente React original ni sus dependencias
  (Next.js, hooks) — se porta solo el resultado visual a JS plano.

## Verificación

Manual:

1. Abrir la app, confirmar que el panel central muestra el arte ASCII de
   la calavera (blanco sobre negro, glitch rojo/azul sutil) en vez del
   texto plano de la Fase 08, escalado correctamente al tamaño del panel.
2. Iniciar sesión de voz (botón de la Fase 08), confirmar que el patrón
   cambia a la variante "escuchando" (glitch más frecuente).
3. Hacer que el asistente responda algo, confirmar que cambia a la
   variante "hablando" (ruido de caracteres) mientras dura la respuesta,
   y vuelve a "inactivo" al terminar.
4. Confirmar que ningún otro elemento de la interfaz tomó color por
   error — el rojo/azul debe verse únicamente en el panel ASCII.

## Entregable final de la fase

- Arte base de la calavera portado a `Jarvis/assets/app.js` (vanilla JS,
  sin React), con auto-escalado por `ResizeObserver`.
- Las 4 variantes de estado (inactivo/escuchando/hablando/procesando)
  moduladas sobre ese mismo arte, según la sección 2.
- `Jarvis/tools/convertir_ascii.py` (Modo A, herramienta de desarrollo
  para material futuro, no bloqueante para esta fase).
- Endpoint `/api/estado` en `server.py`.
- Reactividad de estado + transición `.glitch` funcionando.
- Marcar `- [x] Fase 09` en `plans/README.md`.
