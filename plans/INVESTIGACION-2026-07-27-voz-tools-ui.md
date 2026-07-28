# Investigación — Fluidez de voz, herramientas, navegador, personaje y animación ASCII

**Fecha:** 2026-07-27
> **Nota de lectura (importante):** las secciones 6 y 10.10 investigan la
> conversión de video a arte ASCII. **Esa dirección quedó descartada** por
> decisión posterior del usuario: el personaje va a ser un sprite 2D animado
> (GIF). La sección **13** documenta ese cambio y qué partes del plan se caen.
> Las secciones sobre ASCII se conservan como registro de por qué se decidió lo
> que se decidió, no como trabajo pendiente.

**Alcance:** SOLO investigación. No se tocó ni una línea de código de la app en
esta sesión. Este documento existe para alimentar fases futuras (11+), arreglos
de bugs y decisiones de diseño.

**Cómo leerlo:** cada área tiene (1) qué pasa hoy con referencia a
`archivo:línea`, (2) causa raíz o hipótesis con evidencia, (3) qué dice la
documentación oficial, (4) opciones concretas con su costo. Al final hay un
flujo de trabajo propuesto y las fuentes.

---

## 0. Resumen ejecutivo — los 8 hallazgos que más importan

| # | Hallazgo | Área | Confianza |
|---|---|---|---|
| 1 | **Hoy es imposible interrumpir a Jarvis por voz (barge-in)**: mientras habla, el micrófono manda silencio puro al servidor. `voice_engine.py:264-265` | Fluidez | Confirmado por código |
| 2 | **Se pierden los primeros ~600 ms de lo que dice el usuario después de cada respuesta** (`_UMBRAL_HABLANDO_S = 0.6`, `voice_engine.py:48`). Es la causa más probable de "me llegan las palabras cortadas". | Palabras cortadas | Alta |
| 3 | **`input_transcription` NO es lo que el modelo entiende**: es un ASR aparte, con bugs documentados por Google (devuelve otro idioma, otras letras). Lo que se ve en pantalla puede estar mal aunque el modelo haya entendido bien. | Palabras cortadas | Confirmado (docs + foro oficial) |
| 4 | **Las tools bloquean la conversación**: `buscar_web` hace un `generate_content` sincrónico completo y `open_app` escanea el menú inicio con `rglob("*.lnk")`. La Live API soporta `behavior: NON_BLOCKING` + `scheduling`, hoy sin usar. | Fluidez / tools | Confirmado (docs) |
| 5 | **El navegador falla por el selector de perfiles de Chrome**: hay 9 perfiles en esta máquina y `picker_shown: true`. `webbrowser.open()` no puede saltarlo; `--profile-directory` sí. | Navegador | Confirmado en el sistema real |
| 6 | **No hay animación real**: `skull_frame.json` tiene UN frame de 99×400 caracteres. `convertir_ascii.py` (el conversor de mp4) existe y funciona, pero su salida nunca se generó ni se conectó a `app.js`. | Animación | Confirmado |
| 7 | **El VAD explícito rompió la sesión antes** (`plans/ERRORES.md`, Fase 06) — pero hay una explicación probable: `silence_duration_ms` por debajo de 500 ms fragmenta el habla; la doc recomienda 500-800 ms. Se puede reintentar con valores seguros. | Fluidez | Hipótesis fuerte |
| 8 | **La calavera flotante NO se puede hacer con pywebview**: `transparent=True` no está soportado en Windows (`ui.py:39` no hace nada). Pero `tkinter` sí puede, con `-transparentcolor` — **probado en esta máquina**. Ver sección 10 | Personaje | Confirmado (spike propio) |
| 9 | **El agente de texto no tiene NINGUNA instrucción de sistema** (`gemini_agent.py:172`): sin persona, sin idioma, sin estilo. Explica el tono inconsistente entre hablarle y escribirle | Prompt | Confirmado por código |
| 10 | **Recordatorios y voz Live viven en universos separados**: el runner avisa con TTS local (`pyttsx3`), no por la sesión Live. Nunca se cruzan, y si suena mientras Jarvis habla, se pisan. | Recordatorios | Confirmado por código |

---

## 1. Mapa del sistema actual (para no re-derivarlo)

```
ui.py           → pywebview: ventana principal + mini PIP; Flask en thread aparte
  server.py     → Flask 127.0.0.1:5577, endpoints REST + estáticos
    gemini_agent.py   → texto: matcher local → Gemini function-calling → tools
    voice_engine.py   → voz: sesión Live API bidireccional; delega tools en el agente
      actions/{tareas, recordatorios, open_app, musica}.py
    matcher.py        → regex/keywords, ahorra cuota
  assets/{index.html, app.js, style.css, skull_frame.json}
```

Datos relevantes del entorno real:

- La app corre con el **Python global** (`C:\Users\danie\AppData\Local\Programs\Python\Python312`), donde vive `google-genai 2.14.0`. El `.venv/` del repo **no tiene `google-genai` instalado** — cualquier script de verificación que se corra con `.venv/Scripts/python.exe` va a fallar con `ModuleNotFoundError: No module named 'google'`. Conviene unificar esto antes de seguir.
- Modelos en uso: `gemini-flash-latest` (texto, `gemini_agent.py:136`) y `gemini-2.5-flash-native-audio-latest` (voz, `voice_engine.py:47`).
- Frecuencias de polling del frontend: estado 500 ms, transcripción 700 ms, estado de voz 3000 ms (`app.js:295,317,473`).

---

## 2. Área A — Latencia y cadencia de la conversación

### 2.1 Dónde se va el tiempo hoy

Recorriendo el camino completo de un turno:

| Etapa | Costo actual | Fuente |
|---|---|---|
| Captura de mic | chunks de 30 ms, 16 kHz mono PCM16 | `voice_engine.py:43,168-173` |
| Detección de fin de turno (VAD servidor) | ~800 ms por defecto | doc Live API |
| **Mordida post-respuesta** | **+600 ms de mic muteado** | `voice_engine.py:48,264` |
| Razonamiento + tools | variable, bloqueante | ver 2.3 |
| Primer audio de salida | sin buffer de jitter, se escribe apenas llega | `voice_engine.py:227-239` |
| Refresco de pantalla | hasta 500-700 ms de retraso | `app.js:473,317` |

### 2.2 Bug de fluidez #1 — no se puede interrumpir (barge-in muerto)

`voice_engine.py:264-265`:

```python
if self.hablando:
    chunk = b"\x00" * len(chunk)
```

Mientras Jarvis habla, el micrófono manda **ceros**. El VAD del servidor nunca
detecta habla, así que `server_content.interrupted` (manejado en
`voice_engine.py:296`) **no puede dispararse nunca desde la voz del usuario**. El
código de barge-in existe pero está muerto.

Esto se hizo para matar el eco (parlante y mic en el mismo equipo) y la decisión
está bien documentada, pero el costo es que la conversación deja de ser
conversación: hay que esperar a que Jarvis termine cada frase.

**Opciones, de más barata a más cara:**

1. **Auriculares + flag en config** (`usar_auriculares: true` → no silenciar).
   Cero código nuevo de audio, barge-in perfecto. Es lo que la propia nota
   `ponytail` en `voice_engine.py:262` ya anticipa.
2. **Gate por energía en vez de mute total**: en vez de ceros, calcular RMS del
   chunk y mandar el audio real solo si supera un umbral bastante por encima del
   nivel del eco. Unas 10 líneas, sin dependencias.
3. **AEC real** (`speexdsp`, `webrtc-audio-processing`, `pyaec`): la solución
   correcta, pero es una dependencia nativa nueva en Windows — costo alto para
   un proyecto personal.

### 2.3 Bug de fluidez #2 — las tools bloquean el turno entero

Hoy, cuando la Live API pide una tool (`voice_engine.py:329-342`), el código
ejecuta la función y **recién después** manda la respuesta. Todo ese tiempo
Jarvis está mudo. Los peores casos medibles:

- **`buscar_web`** (`gemini_agent.py:208-240`): hace un `generate_content` COMPLETO
  con grounding, en otra request. Son segundos, no milisegundos.
- **`open_app`** paso 5 (`open_app.py:244-270`): `rglob("*.lnk")` recursivo sobre
  las DOS carpetas de Menú Inicio, sin caché. En un equipo con muchos programas
  esto puede tardar cientos de ms a segundos, y se repite en cada invocación.
- **`musica` → `buscar_youtube`** (`musica.py:13-32`): scraping HTTP sincrónico.

**La solución oficial existe y no se está usando: función asíncrona.** De la
documentación de tool use de la Live API:

```python
turn_on_the_lights = {"name": "turn_on_the_lights", "behavior": "NON_BLOCKING"}
```

y al responder:

```python
function_response = types.FunctionResponse(
    id=fc.id,
    name=fc.name,
    response={
        "result": "ok",
        "scheduling": "INTERRUPT"   # o "WHEN_IDLE" o "SILENT"
    }
)
```

Semántica de `scheduling`:

- `INTERRUPT` — corta lo que esté diciendo y reporta ya. Para "abrí Chrome": el
  usuario quiere confirmación inmediata.
- `WHEN_IDLE` — espera a que termine de hablar y ahí lo reporta. Ideal para
  `buscar_web`: Jarvis puede decir "dame un segundo, lo busco" y entregar el
  resultado cuando lo tiene.
- `SILENT` — lo guarda como conocimiento sin decir nada. Ideal para tools de
  contexto (ej. refrescar la lista de tareas sin narrarlo).

**Restricción importante:** la doc dice explícitamente que *"Asynchronous
function calling is not yet supported in Gemini 3.1 Flash Live"* — funciona con
**Gemini 2.5 Flash Live**, que es justamente la familia que este proyecto usa.
Es decir: se puede adoptar hoy, pero fija el proyecto a la familia 2.5 mientras
3.1 no lo soporte.

**Complemento barato y de gran impacto percibido:** frases de relleno. Instruir
por `system_instruction` que ante una tool lenta diga algo corto ("un segundo,
señor") antes de esperar. Es el truco estándar de los asistentes de voz y no
cuesta ni una línea de infraestructura.

### 2.4 VAD — recalibrar sin repetir el desastre de la Fase 06

`plans/ERRORES.md` (Fase 06, cuarta entrada) documenta que agregar
`realtime_input_config` dejó al servidor completamente mudo, con
`START_SENSITIVITY_LOW` y con `HIGH`. La entrada dice "causa no determinada".

La documentación oficial da una pista concreta que la entrada no considera:

> "The `silenceDurationMs` value directly affects the size and completeness of
> audio chunks the model receives for processing." Valores recomendados:
> **500–800 ms**. Por debajo de 500 ms se fragmenta el habla en pausas naturales.

Y el ejemplo que la propia doc muestra usa `silence_duration_ms: 100` — un valor
que la misma página después desaconseja. Si la implementación de la Fase 06 copió
ese ejemplo, el habla se fragmentaba en pedazos diminutos, y un stream de
fragmentos de 100 ms puede perfectamente derivar en el comportamiento observado.

Campos reales disponibles (`realtimeInputConfig.automaticActivityDetection`):

| Campo | Default | Nota |
|---|---|---|
| `disabled` | `false` | ponerlo en `true` obliga a mandar `activityStart`/`activityEnd` a mano |
| `start_of_speech_sensitivity` | — | `START_SENSITIVITY_LOW` / `HIGH` |
| `end_of_speech_sensitivity` | — | `END_SENSITIVITY_LOW` / `HIGH` |
| `prefix_padding_ms` | 20 ms | audio incluido ANTES de detectar habla |
| `silence_duration_ms` | ~800 ms servidor | **no bajar de 500** |

**Recomendación de prueba (una variable por vez, con log de timestamps como ya
hizo la Fase 06):**

1. Primero solo `prefix_padding_ms: 300`, nada más. Sirve directo contra
   "palabras cortadas al principio": 20 ms de padding es muy poco margen.
2. Si eso sobrevive, agregar `silence_duration_ms: 600`.
3. Recién al final tocar sensibilidades.

Si el servidor se vuelve a quedar mudo con el paso 1 aislado, entonces sí es el
campo en sí y no el valor, y hay que documentarlo como limitación del modelo
`gemini-2.5-flash-native-audio-latest` con esta cuenta.

**Alternativa si el VAD del servidor sigue sin ser confiable: VAD local.**
Deshabilitar el automático (`disabled: true`) y mandar `activity_start` /
`activity_end` desde Python usando `webrtcvad` o `silero-vad`. Da control total
sobre cuánto silencio cierra el turno, y como bonus permite **wake word** ("oye
Jarvis") sin mandar audio continuo a Google.

```python
await session.send_realtime_input(activity_start=types.ActivityStart())
await session.send_realtime_input(
    audio=types.Blob(data=audio_bytes, mime_type="audio/pcm;rate=16000")
)
await session.send_realtime_input(activity_end=types.ActivityEnd())
```

### 2.5 Modelos: qué hay disponible hoy

La documentación de capacidades lista:

- `gemini-3.1-flash-live-preview` — el más nuevo. Turn coverage por defecto
  `TURN_INCLUDES_AUDIO_ACTIVITY_AND_ALL_VIDEO`. Usa `thinkingLevel`
  (`minimal`/`low`/`medium`/`high`) — **`minimal` es la palanca directa de
  latencia**. Pero: **no soporta function calling asíncrono**.
- `gemini-2.5-flash-native-audio-preview-12-2025` — familia actual del proyecto.
  Turn coverage `TURN_INCLUDES_ONLY_ACTIVITY`. Usa `thinkingBudget` (en tokens),
  con thinking dinámico activado por defecto. Soporta async function calling,
  proactive audio y affective dialog.

**Ojo con el alias en uso:** `voice_engine.py:47` usa
`gemini-2.5-flash-native-audio-latest`. Ese sufijo `-latest` **no aparece en la
documentación de capacidades**; la doc nombra
`gemini-2.5-flash-native-audio-preview-12-2025`. Funciona hoy (probado en la
Fase 06) pero es un alias no documentado — vale la pena confirmarlo con
`client.models.list()` filtrando por `live`/`audio` cada tanto, y tener el nombre
con fecha como fallback.

Palanca de latencia concreta y barata: **bajar el thinking**. En 2.5,
`thinkingBudget` chico o cero; si algún día se migra a 3.1,
`thinkingLevel: "minimal"`. Para un asistente de escritorio que sobre todo
ejecuta tools y responde corto, el razonamiento profundo es tiempo tirado.

### 2.6 Límites de sesión que hoy no se manejan

| Límite | Valor | Estado en el proyecto |
|---|---|---|
| Sesión solo audio | **15 minutos** | **No manejado** — a los 15 min se corta |
| Sesión audio + video | 2 minutos | no aplica |
| Ventana de contexto (native audio) | 128k tokens | no manejado |
| Consumo de audio | ~25 tokens por segundo | no manejado |

A ~25 tokens/segundo, una sesión larga consume contexto rápido. Las dos
herramientas oficiales:

```python
live_config = types.LiveConnectConfig(
    context_window_compression=types.ContextWindowCompressionConfig(
        trigger_tokens=100_000,
        sliding_window=types.SlidingWindow(target_tokens=4_000),
    ),
)
```

- **`context_window_compression`** — ventana deslizante del lado del servidor que
  descarta los turnos más viejos al pasar `trigger_tokens`. Advertencia de la
  doc: esto **causa pérdida de historial**; un `target_tokens` muy bajo hace que
  el modelo olvide rápido.
- **`session_resumption`** — el servidor manda periódicamente un handle; si se
  cae la conexión, se reconecta pasando ese handle y el contexto sobrevive. Se
  puede cambiar cualquier parámetro de configuración al reanudar **menos el
  modelo**. Esto es lo que arreglaría de raíz el corte a los 15 minutos y las
  reconexiones que la Fase 06 vio en los logs.

Hay un bug abierto conocido (`googleapis/python-genai#2290`): la reanudación se
vuelve inestable después de haber usado audio+video; solo audio reanuda bien. Como
este proyecto es solo audio, no debería afectar.

---

## 3. Área B — "Le llegan las palabras cortadas u otra palabra con otras letras"

Este síntoma tiene **tres causas independientes** que conviene no mezclar.

### 3.1 Causa A — la mordida de 600 ms (probablemente la principal)

`voice_engine.py:70-79` define `hablando` como: hay audio en cola **o** pasaron
menos de `_UMBRAL_HABLANDO_S = 0.6` segundos desde el último audio escrito. Y
`_enviar_audio` reemplaza el mic por silencio mientras `hablando` sea `True`.

Consecuencia directa: **los primeros 600 ms de lo que el usuario diga apenas
termina Jarvis se envían como silencio digital.** Si el usuario responde rápido
—que es exactamente lo que uno hace en una conversación fluida— la primera
palabra llega mutilada o directamente no llega.

Y como el `prefix_padding_ms` por defecto es de solo 20 ms, no hay ningún margen
del lado del servidor que compense.

**Es la hipótesis que mejor explica el síntoma reportado y la más barata de
probar:** bajar el umbral, o eliminarlo usando auriculares, o reemplazarlo por
el gate de energía de 2.2.

### 3.2 Causa B — el transcript no es lo que el modelo entiende

Hallazgo importante y contraintuitivo, confirmado en el foro oficial de Google
AI: **`input_audio_transcription` corre un ASR separado del entendimiento del
modelo.** Hilos documentados:

- *"Gemini Live API: input_audio_transcription returns incorrect text while model
  correctly processes audio"* — el texto que llega no coincide con lo que el
  modelo entendió, aunque el modelo respondió bien.
- *"Input transcription in gemini live api is very weird"* — inglés hablado que
  vuelve transcripto con caracteres de otro alfabeto (hindi, símbolos ilegibles).
- *"Gemini Live API Transcription sometimes shows incorrect language"*
  (livekit/agents#3551).
- *"Delays or Missing input_audio_transcription Events"* — truncamiento en turnos
  largos con pausas naturales.

**Implicación práctica para este proyecto:** si el usuario dice "abrí Chrome",
Jarvis lo hace bien, pero en pantalla aparece "abrí crome" — eso **no es un bug
de Jarvis y no se arregla en este código**. Es un defecto conocido del servicio.

Consecuencias de diseño:

1. **Nunca alimentar lógica con el texto de `input_transcription`.** Hoy no se
   hace (bien: la Live API decide las tools por su cuenta,
   `voice_engine.py:329`), pero es una tentación obvia a futuro — por ejemplo,
   pasar la transcripción por `matcher.py` para ahorrar cuota. **No hacerlo**:
   el matcher recibiría texto corrupto y ejecutaría acciones equivocadas.
2. En la UI, considerar marcar visualmente el transcript del usuario como
   aproximado (opacidad menor, o una nota) para que no parezca un bug propio.

### 3.3 Causa C — fragmentación por VAD

Del mismo cuerpo de reportes: cuando los umbrales de VAD son demasiado bajos
(100-200 ms), el sistema cierra el turno en pausas naturales y parte la frase en
fragmentos chicos; el modelo pierde el contexto entre fragmentos y la calidad de
transcripción baja. Es la contracara del punto 2.4: es un argumento para NO bajar
`silence_duration_ms`, aunque bajarlo parezca "más rápido".

### 3.4 Palanca que hoy no se usa: fijar el idioma

La Live API soporta 97 idiomas con códigos BCP-47 (`es`, `en`, ...). Hoy el
proyecto **no configura ninguno** — la instrucción de sistema
(`voice_engine.py:36-39`) pide español en prosa, pero eso no es lo mismo que
declarar el idioma de reconocimiento. Fijar el idioma explícitamente es la
defensa directa contra el bug de "transcribe a otro alfabeto".

Nota sobre el español rioplatense: la instrucción de sistema usa "Sos" y
"Respondé". Si el usuario habla español colombiano (el correo y el contexto lo
sugieren), conviene revisar si eso es intencional — puede afectar tanto el tono
de las respuestas como, en menor medida, las expectativas del reconocimiento.

---

## 4. Área C — Herramientas: abrir apps, buscar en YouTube, navegador

### 4.1 El problema del navegador, medido en esta máquina

Se leyó el `Local State` de Chrome (solo lectura). Resultado real:

```
Default    -> daniel   | danieltriana1125@gmail.com
Profile 2  -> daniel   | danieltriana1126@gmail.com
Profile 3  -> Daniel   | danieltriana112501@gmail.com
Profile 4  -> Area     | analistalogistico111@gmail.com
Profile 5  -> Daniel   | d64544333@gmail.com
Profile 6  -> daniel   | daniel.gomez.dev.co@gmail.com
Profile 7  -> Dany     | dany.andres1126@gmail.com
Profile 8  -> Dankel   | dtandres1125@gmail.com
Profile 9  -> CALIDAD& | copiadeseguridad.cge12@gmail.com

last_used: 'Profile 4'
picker_shown: true
```

Y el navegador por defecto del sistema es `ChromeHTML` (Chrome).

Eso explica **exactamente** los dos síntomas reportados:

- **"a veces no lo abre"** — `webbrowser.open()` (`musica.py:60`,
  `gemini_agent.py:231`) delega en ShellExecute. Si ya hay una instancia de
  Chrome corriendo, la URL va a esa ventana, que puede quedar detrás de la
  ventana de Jarvis (que además es `on_top=True` para el mini PIP,
  `ui.py:38`) — se abrió, pero no se ve.
- **"otras veces no deja porque tiene que seleccionar una cuenta"** — con 9
  perfiles y `picker_shown: true`, Chrome muestra el selector de perfiles y se
  queda esperando un clic humano. Jarvis no puede resolverlo.

### 4.2 La solución: lanzar Chrome con perfil explícito

Chrome acepta `--profile-directory`:

```
chrome.exe --profile-directory="Profile 5" https://youtube.com/watch?v=...
```

**Trampa documentada y crítica:** el valor **no es el nombre visible del
perfil**, es el nombre de la CARPETA (`Default`, `Profile 2`, `Profile 5`...). En
esta máquina hay cuatro perfiles llamados "daniel"/"Daniel" con carpetas
distintas — usar el nombre visible es directamente ambiguo. La forma de
verificar cuál es cuál es `chrome://version` → campo "Profile Path", o leer el
`info_cache` del `Local State` como se hizo arriba.

**Diseño propuesto (para una fase futura, NO implementado):**

1. Nueva clave en `config.py`: `chrome_profile_dir` (por defecto `""` = usar el
   comportamiento actual).
2. Endpoint `GET /api/chrome-profiles` que lea `Local State` y devuelva
   `[{dir, nombre, email}]` — mismo patrón que ya se usó para
   `/api/audio-devices`, y por la misma razón: **listar desde el backend, no
   adivinar desde el frontend** (regla ya aprendida en `plans/ERRORES.md`, Fases
   08/09).
3. Selector en el modal de Configuración, mostrando `nombre — email` pero
   guardando la carpeta.
4. Un único helper `abrir_url(url)` compartido por `musica.py` y
   `gemini_agent.py`, que use el perfil si está configurado y caiga a
   `webbrowser.open()` si no.

**Importante — punto de seguridad:** ese helper es un camino nuevo hacia
`subprocess`, y la URL puede venir de la salida de un modelo. Debe validar el
esquema (solo `http`/`https`) y pasar los argumentos **como lista**, nunca con
`shell=True`. `open_app.py:199` ya tiene el guard `_SHELL_METACHARS` justamente
por esta clase de riesgo (`plans/ERRORES.md`, Fase 04) — no repetir el error en
un módulo nuevo.

### 4.3 Latencia y fragilidad de las otras tools

- **`open_app` sin caché**: el escaneo del Menú Inicio (`open_app.py:244-270`)
  se rehace en cada llamada fallida de los pasos previos. Un índice cacheado en
  `datos/` (con invalidación por fecha de modificación de las carpetas) elimina
  el peor caso. Alternativa más lazy: caché en memoria por proceso, se pierde al
  reiniciar y alcanza.
- **`youtube-search-python` es una bomba de tiempo**: versión 1.6.6, publicada en
  2021, sin mantenimiento, y ya rompió dos veces por `httpx` (`plans/ERRORES.md`,
  Fases 04 y 05). Hoy sostiene un pin `httpx<0.28` que **entra en conflicto
  declarado con `google-genai`** (que pide `>=0.28.1`), y funciona solo por
  suerte. Alternativas: `yt-dlp` (mantenido, más pesado), o el scraping directo
  de `youtube.com/results?search_query=` que la nota `ponytail` en `musica.py:10`
  ya deja anotado como salida de emergencia. **Sacarse de encima este pin
  debería ser prioritario** — bloquea actualizar `google-genai`, que es la
  librería central del proyecto.
- **`buscar_web` devuelve 429 por cuota de grounding** (`plans/ERRORES.md`, Fase
  05). Sigue pendiente y **no se arregla con código**: requiere billing
  habilitado. Ver también el punto 8.2 sobre el formato de la API key.

### 4.4 Combinar `google_search` con tools propias: la doc dice que sí (en Live)

`gemini_agent.py:5-9` documenta que la API **rechaza** mezclar `google_search`
con `function_declarations` en la misma request, y por eso `buscar_web` hace una
request separada. Eso fue verificado empíricamente para `generate_content`.

Pero para la **Live API** la documentación muestra lo contrario, explícitamente:

```python
tools = [
    {"google_search": {}},
    {"function_declarations": [turn_on_the_lights, turn_off_the_lights]},
]
```

y la tabla de modelos confirma que Gemini 2.5 Flash Live soporta "Search, sync
and async functions" en simultáneo.

**Implicación:** en la sesión de voz, la búsqueda podría hacerla la propia Live
API con grounding nativo, sin el ida y vuelta a `buscar_web` (que hoy cuesta una
request extra y un turno bloqueado). Vale la pena probarlo — con la salvedad de
que la cuota de grounding sigue siendo la misma restricción de cuenta.

---

## 5. Área D — Selector de personaje (cambiar la calavera)

Hoy la calavera está cableada: `app.js:365` hace `fetch("/skull_frame.json")`,
un archivo fijo. No hay nada que cambiar de personaje.

Nada de esto requiere investigación externa; es diseño. La forma más lazy que
funciona:

**Formato de personaje** — un JSON por personaje en `Jarvis/assets/personajes/`:

```json
{
  "id": "calavera",
  "nombre": "Calavera",
  "charset": " .:░▒▓█",
  "fps": 12,
  "frames": [["fila", "fila", ...], ...]
}
```

Con `frames` de longitud 1 se cubre el caso estático actual sin ningún código
especial — el personaje actual se migra a este formato y deja de ser un caso
aparte. (Nota: hoy `skull_frame.json` guarda `{"frame": "<string con \n>"}` y
`convertir_ascii.py` emite `{"fps": N, "frames": [[...]]}`: **son dos formatos
incompatibles**. Unificar en el segundo, que es el que ya genera el conversor.)

**Lo mínimo que hace falta:**

1. `GET /api/personajes` — lista los `.json` de esa carpeta leyendo solo `id` y
   `nombre` (no cargar los frames para listar).
2. Clave `personaje` en `config.py` (por defecto `"calavera"`).
3. `app.js` pide `/personajes/{id}.json` en vez del archivo fijo.
4. Selector en el modal de Configuración, al lado del de voz.

**Lo que NO hace falta y conviene no construir:** sistema de packs, thumbnails,
previsualización animada, descarga de personajes. Agregar un personaje debe ser
"copiar un JSON a la carpeta", nada más.

**Detalle visual a respetar:** cada personaje debería declarar su propio
`charset`, porque `ASCII_CHARSET` (`app.js:340`) se usa para el ruido del estado
"hablando" — si el arte usa `" .:-=+*#%@"` (la rampa de `convertir_ascii.py:22`)
y el ruido mete `░▒▓█`, el glitch se ve fuera de lugar.

---

## 6. Área E — La animación ASCII real del mp4

### 6.1 Qué hay hoy, medido

- `assets/skull_frame.json` = **un solo frame**, clave `"frame"`, string de
  39.698 caracteres → **99 líneas × 400 columnas**.
- Lo que se percibe como "animación" son dos efectos CSS/JS sobre ese frame
  único: un glitch periódico (`app.js:405-420`) y ruido aleatorio de 1-3% de los
  caracteres solo en estado "hablando" (`app.js:422-431`).
- `plans/phase-09-ascii-panel.md` lo dice explícito: *"el array FRAMES del
  original tiene longitud 1 — no es una animación cuadro a cuadro real"*.
- `Jarvis/tools/convertir_ascii.py` **existe, está completo y funciona**: toma un
  mp4, lo pasa a escala de grises, remuestrea con corrección de aspecto
  (`FACTOR_ASPECTO_CHAR = 0.55`) y emite
  `{"fps": N, "frames": [[fila, fila, ...], ...]}`.

**Conclusión: la brecha no es técnica, es de ejecución.** Falta (a) correr el
conversor sobre el mp4, (b) que `app.js` sepa reproducir múltiples frames.

### 6.2 Presupuesto de tamaño y rendimiento — lo que hay que cuidar

Es el único punto donde esto se puede ir de las manos. Cuentas concretas:

| Config | Chars/frame | 60 frames | 120 frames |
|---|---|---|---|
| 400 cols (actual) × 99 filas | 39.600 | ~2,4 MB | ~4,8 MB |
| 100 cols × 27 filas | 2.700 | ~160 KB | ~320 KB |
| 160 cols × 44 filas | 7.040 | ~420 KB | ~845 KB |

El default de `convertir_ascii.py` es `--cols 100`, que cae en la fila cómoda. El
arte actual a 400 columnas es **cuatro veces más ancho** que ese default: animarlo
a esa resolución es innecesariamente caro. Y el panel ya se reescala a
`ALTURA_MAX_PANEL_ASCII = 260` px (`app.js:382`), así que ese detalle extra
tampoco se ve.

**Recomendación:** `--cols 120 --fps 12`, y **recortar el video a un loop corto**
(2-4 segundos). Un loop corto que cicla bien vale más que 30 segundos de
animación en un panel de 260 px de alto.

**Rendimiento del reproductor:** hoy `renderAscii()` (`app.js:375-377`) hace
`textContent = asciiChars.join("")` sobre un array de caracteres sueltos. Para 60
frames eso es un `join` de 40.000 elementos, 12 veces por segundo — desperdicio
puro. Con frames pre-renderizados basta con guardar cada frame ya unido como
string y asignar `textContent` directo. Un `requestAnimationFrame` con
acumulador de tiempo es preferible a `setInterval` para el ritmo.

**Cómo conviven animación y estados:** la decisión de diseño está pendiente. Dos
caminos:

- **A (lazy):** el loop de frames corre siempre; los cuatro estados siguen siendo
  modulaciones encima (velocidad del loop, intensidad del glitch, ruido). Reusa
  toda la lógica ya escrita en `app.js:447-459`.
- **B (completo):** cada estado tiene su propia secuencia de frames (4 clips).
  Cuatro veces el peso y cuatro videos que producir; solo vale la pena si el
  usuario ya tiene ese material.

Si no hay material específico por estado, **A**.

### 6.3 Nota práctica

`convertir_ascii.py` necesita `opencv-python`, que **no está en
`requirements.txt`** a propósito (`convertir_ascii.py:9-11`). Es una herramienta
de desarrollo. Al instalarlo, aplicar la regla ya aprendida en
`plans/ERRORES.md`: después de cualquier `pip install` nuevo, **re-verificar el
pin de `httpx`**, que ya se rompió dos veces por esto.

---

## 7. Área F — Que recordatorios y tareas fluyan igual de bien

### 7.1 El problema estructural: dos bocas separadas

Hoy hay **dos sistemas de voz que no se conocen**:

| | Voz Live (Gemini) | Runner de recordatorios |
|---|---|---|
| Motor | `voice_engine.py`, Live API | `tts_local.py`, `pyttsx3` |
| Cuándo habla | en sesión activa | cuando vence un recordatorio |
| Voz | la elegida en config (Puck/Kore/...) | voz del sistema Windows |
| Se coordinan | **no** | **no** |

`server.py:246` arranca el runner con `_start_runner(hablar, agente=...)`. Si un
recordatorio vence **mientras Jarvis está hablando por la Live API**, las dos
voces salen por el mismo parlante al mismo tiempo. Y peor: el TTS local sale por
el parlante, el mic lo capta, y el VAD del servidor lo interpreta como que el
usuario está hablando.

Además el cambio de voz es abrupto y rompe la ilusión de que es un mismo
asistente.

### 7.2 Camino recomendado: inyectar eventos en la sesión Live

La Live API acepta contenido de texto en medio de una sesión de audio. Es decir,
cuando un recordatorio vence **y hay sesión de voz activa**, en vez de invocar
`pyttsx3` se le puede mandar al modelo algo como:

> "(evento del sistema) Vencio el recordatorio: sacar la basura. Avisale al
> usuario con naturalidad."

Y que Jarvis lo diga **con su propia voz, en el momento oportuno**, respetando el
turno en curso.

Si no hay sesión activa, se mantiene el TTS local como fallback — que es
exactamente lo que ya hace hoy.

**El `scheduling` de la sección 2.3 encaja acá de forma natural:**

- Recordatorio que vence → `INTERRUPT` (es urgente, corta).
- Tarea completada en la UI mientras se conversa → `SILENT` (que el modelo lo
  sepa, sin narrarlo).
- Resumen matutino (Fase 07, pendiente) → `WHEN_IDLE`.

### 7.3 Proactive audio: la pieza que faltaba para que no sea molesto

Función disponible **solo en Gemini 2.5 Flash Live** (no en 3.1), requiere versión
de API `v1alpha`:

```python
proactivity: {'proactive_audio': True}
```

De la doc: *"the model can proactively decide not to respond if the input content
is not relevant"*.

Para un asistente siempre escuchando, esto es exactamente lo que hace falta: hoy
el modelo intenta responder a cualquier cosa que el VAD marque como habla —
incluido el ruido de fondo, una conversación ajena, o la tele. Con proactive audio
puede callarse. Es la diferencia entre un asistente que se puede dejar prendido y
uno que hay que apagar.

Su compañero, **affective dialog** (`enable_affective_dialog: true`, también
`v1alpha` y solo 2.5): el modelo adapta tono y estilo a la expresión del usuario.
Barato de probar, encaja con el carácter que el proyecto busca.

**Costo de adoptar los dos:** fijarse a `v1alpha` y a la familia 2.5. Sumado a
que el function calling asíncrono también es solo-2.5, la conclusión es clara:
**quedarse en Gemini 2.5 Flash Live por ahora**; 3.1 todavía no tiene las tres
funciones que este proyecto más necesita.

### 7.4 Otros puntos sueltos de tareas/recordatorios

- **Intervalo del runner de 10 s** (`plans/ERRORES.md`, Fase 03): un recordatorio
  para "las 9:00" puede sonar a las 9:00:09. Aceptable, pero si se quiere
  precisión, dormir hasta el próximo vencimiento en vez de hacer polling fijo.
- **La UI no se entera de los disparos**: si un recordatorio suena con la app
  abierta, no aparece nada en pantalla. El endpoint `/api/estado` ya se consulta
  cada 500 ms — agregarle un campo de eventos recientes es casi gratis.
- **`/api/estado` no conoce a los recordatorios**: durante un aviso, el estado
  sigue diciendo "escuchando" mientras el TTS local habla. El panel ASCII
  entonces miente.
- **Tareas y recordatorios están separados por diseño** (`tareas.json`,
  `recordatorios.json`, `alarmas.json`) y está bien — no unificarlos. Lo que sí
  falta es que una tarea con fecha y hora pueda generar su recordatorio sin que el
  usuario lo pida dos veces.

---

## 8. Riesgos y bugs abiertos detectados de paso

### 8.1 Entorno Python dividido

El `.venv/` del repo no tiene `google-genai`; la app corre con el Python global.
Cualquiera que clone el repo y use el venv obtiene `ModuleNotFoundError`. Decidir
uno de los dos y documentarlo en el README.

### 8.2 La API key: seguridad y formato

**Advertencia de seguridad.** La API key de Gemini está guardada en texto plano en
`Jarvis/datos/settings.json`. Eso es una decisión deliberada y documentada del
proyecto (uso personal, sin encriptación) y el archivo **sí está en `.gitignore`
y no está trackeado por git** — verificado. No hay filtración a repositorio.

Dicho eso, dos cosas a tener en cuenta:

1. Esa clave quedó visible en el log de esta sesión de trabajo al inspeccionar la
   configuración. Si esa sesión se comparte o se sube a algún lado, la clave se
   comparte con ella. Rotarla en Google AI Studio es barato y es la decisión
   prudente.
2. **El valor guardado empieza con `AQ.Ab8RN6...`**, no con `AIza...` que es el
   prefijo de las API keys de Gemini. Puede ser un token de otro tipo (modo
   express / credencial efímera). Vale la pena verificarlo, porque **podría ser
   la explicación real del 429 de grounding** que la Fase 05 atribuyó a falta de
   billing — un tipo de credencial equivocado da errores de cuota que parecen
   problemas de facturación. Probar con una key `AIza...` recién generada antes
   de habilitar billing.

### 8.3 El conflicto de `httpx` bloquea actualizaciones

`httpx<0.28` (por `youtube-search-python`) contra `google-genai>=0.28.1`. Funciona
por casualidad. Impide actualizar la librería más importante del proyecto. Ver
4.3.

### 8.4 La ventana mini es `on_top=True` siempre

`ui.py:38`. Puede tapar el navegador que Jarvis acaba de abrir, y contribuir a la
sensación de "no lo abrió". Vale la pena revisar si `on_top` debería apagarse
mientras se lanza una app externa.

---

## 9. Flujo de trabajo propuesto (fases 11+)

Ordenado por **impacto percibido dividido por esfuerzo**. Cada fase sigue el
formato de las anteriores: alcance chico, fuera de alcance explícito,
verificación declarada, builder → reviewer → checkbox.

### Tanda 1 — Fluidez (el usuario nota esto de inmediato)

| Fase | Qué | Por qué primero |
|---|---|---|
| **11** | Bajar/eliminar la mordida de 600 ms; flag `usar_auriculares`; gate por energía | Ataca "palabras cortadas" y devuelve el barge-in. Es el cambio más chico de todos |
| **12** | Function calling asíncrono: `NON_BLOCKING` + `scheduling`, frases de relleno, caché del Menú Inicio | Elimina los silencios largos al abrir apps y buscar |
| **13** | Reintento controlado del VAD: `prefix_padding_ms` primero, aislado, con logs | Riesgo conocido — por eso va solo, después de que lo demás esté estable |

### Tanda 2 — Robustez de las herramientas

| Fase | Qué |
|---|---|
| **14** | Perfil de Chrome: `/api/chrome-profiles`, config, helper `abrir_url()` con validación de esquema |
| **15** | Sacar `youtube-search-python`, liberar el pin de `httpx`, actualizar `google-genai` |
| **16** | Sesión: `session_resumption` + `context_window_compression` (mata el corte a los 15 min) |

### Tanda 3 — Presencia y carácter

| Fase | Qué |
|---|---|
| **17** | Formato único de personaje + `/api/personajes` + selector. Migrar la calavera actual |
| **18** | Animación real: correr `convertir_ascii.py` sobre el mp4 (120 cols, 12 fps, loop corto) y reproductor multi-frame en `app.js` |
| **19** | `proactive_audio` + `affective_dialog` (`v1alpha`) |

### Tanda 4 — Cerrar el círculo

| Fase | Qué |
|---|---|
| **20** | Recordatorios por la voz Live cuando hay sesión activa; TTS local como fallback; estado del panel durante un aviso |
| **21** | Fase 07 pendiente (clima + resumen matutino) montada sobre `WHEN_IDLE` |
| **22** | Fase 10 pendiente + eventos de recordatorio visibles en la UI |

### Reglas de trabajo para estas fases

1. **Una variable por vez en todo lo que toque la Live API.** La Fase 06 ya
   demostró que combinar cambios ahí vuelve imposible atribuir la causa.
2. **Instrumentar antes de cambiar.** El logging con timestamps de
   `voice_engine.py` fue lo que resolvió tres bugs seguidos. Antes de tocar
   latencia, medir: tiempo entre el fin del habla y el primer audio de respuesta,
   y duración de cada tool.
3. **Ningún cambio de latencia se da por bueno sin escucharlo.** La regla de
   `plans/ERRORES.md` sobre los self-checks de voz aplica igual: un assert que
   pasa no significa que la conversación se sienta fluida.
4. **Agregar a `plans/ERRORES.md` cada supuesto que resulte falso.** Este
   documento se apoya fuertemente en esa bitácora; mantenerla viva es lo que
   hace que la próxima investigación arranque más arriba.

---

## 10. Área G — La calavera viva: de rectángulo flotante a personaje en el escritorio

Esta es la sección más importante para la visión que el usuario describió:

> "una calavera hablante que esté por ahí… la silueta de la calavera animada, y
> cada vez que hable saque una viñeta diciendo recordatorios y preguntando por
> tareas hechas o pendientes… un asistente personal que moleste en la pantalla
> como si estuviera vivo."

Eso **no es la ventana mini actual**. Es otra cosa, y hay una razón técnica dura
por la que la ventana mini nunca va a poder serlo.

### 10.1 Qué es la calavera hoy, con precisión

| Aspecto | Estado real | Referencia |
|---|---|---|
| Arte | 1 frame, 99 líneas × 400 columnas, 39.698 chars | `assets/skull_frame.json` |
| Formato | `{"frame": "<string con \n>"}` | idem |
| Charset | `" .:░▒▓█"` | `app.js:340` |
| "Animación" | glitch CSS periódico + ruido aleatorio de 1-3% de caracteres, solo en estado "hablando" | `app.js:405-431` |
| Estados | 4 (inactivo/escuchando/hablando/procesando), NO son frames distintos | `app.js:342-354` |
| Escalado | `transform: scale()` con tope de 260 px de alto | `app.js:382-401` |
| Ventana mini | 200×200 px, `frameless`, `on_top`, `transparent=True`, `background_color="#050505"` | `ui.py:16-43` |
| Contenido del mini | la misma página, con CSS que esconde todo menos el panel | `style.css:410-425` |

O sea: la calavera es **una ilustración fija con dos efectos encima**, metida en
un cuadrado negro de 200×200.

### 10.2 Por qué el mini es un rectángulo negro (y no se puede arreglar ahí)

`ui.py:39` pide `transparent=True`. **En Windows, pywebview ignora ese
parámetro: la transparencia no está soportada en el backend de Windows.** Está
documentado en varios issues abiertos del proyecto (#488, #745, #1200, #1271).
Por eso `background_color="#050505"` es lo que se ve: un cuadrado casi negro.

Hay un agravante reportado en el issue #1271: en los casos donde algo de
transparencia sí se aplica, **el mouse atraviesa la ventana entera**, así que se
pierde toda posibilidad de hacerle clic al personaje.

**Conclusión: la idea de la calavera flotante NO se implementa dentro de
pywebview.** Ese camino está cerrado por el motor, no por el código de Jarvis. Es
importante entenderlo antes de gastar una fase intentándolo.

### 10.3 Spike ejecutado: qué SÍ funciona en esta máquina

Se corrió una prueba real (script descartable en el scratchpad, nada tocado en el
repo) para confirmar qué APIs de ventana responden en este Windows concreto:

| Capacidad | API | Resultado |
|---|---|---|
| Ventana sin bordes ni barra | `overrideredirect(True)` | **OK** |
| Siempre encima | `attributes('-topmost', True)` | **OK** |
| **Transparencia por color** | `wm_attributes('-transparentcolor', '#010203')` | **OK** |
| Opacidad global | `attributes('-alpha', 0.9)` | **OK** |
| **Click-through** | `WS_EX_LAYERED\|WS_EX_TRANSPARENT` vía `ctypes` + `SetWindowLongW` | **OK** |
| Mover la ventana | `geometry('+x+y')` | **OK** |
| Versión | Tk 8.6 | — |

**Todo verde, y con `tkinter`, que es librería estándar de Python — cero
dependencias nuevas.**

`-transparentcolor` es exactamente la técnica que usan los desktop pets tipo
Shimeji en Windows: se pinta el fondo de un color clave y el sistema lo vuelve
literalmente invisible, dejando **solo la silueta del contenido**. Para arte
ASCII —texto claro sobre fondo plano— encaja perfecto: queda la calavera
recortada flotando sobre el escritorio, sin ningún rectángulo.

### 10.4 Opciones de implementación, comparadas

| Opción | Silueta real | Click-through | Dependencia nueva | Costo |
|---|---|---|---|---|
| **A. Overlay `tkinter`** | Sí (`-transparentcolor`) | Sí (ctypes) | **ninguna** (stdlib) | Bajo |
| B. Overlay PyQt6 | Sí (`WA_TranslucentBackground`), con alpha real por píxel | Sí | PyQt6 (~60 MB) | Medio |
| C. Seguir en pywebview | **No** — bloqueado en Windows | roto | — | Inviable |

**Recomendación: A.** Es la única que no agrega dependencias, ya está verificada
en esta máquina, y para arte ASCII monocromo el color-key da un resultado
indistinguible del alpha real. PyQt6 solo se justificaría si en el futuro los
personajes fueran PNG con bordes suaves — y ni siquiera entonces es urgente.

**Limitación honesta de A que hay que aceptar de entrada:** `-transparentcolor`
es binario, no tiene semitransparencia. Si el texto se renderiza con
antialiasing, los píxeles del borde mezclan el color del texto con el color clave
y pueden quedar como un halo tenue. Mitigación: elegir un color clave que no
aparezca en el degradado del texto (un magenta puro tipo `#FF00FE`, no negro), y
si el halo molesta, usar una fuente sin antialiasing o subir el tamaño.

### 10.5 Arquitectura propuesta: el overlay es un cliente más

El punto clave de diseño, y lo que lo hace barato: **el overlay no necesita saber
nada de Gemini.** Ya existe toda la infraestructura que precisa.

```
                     Flask 127.0.0.1:5577  (ya existe)
                       │
    ┌──────────────────┼──────────────────────┐
    │                  │                      │
ventana principal   ventana mini          overlay calavera   ← nuevo
 (pywebview)        (pywebview)            (tkinter, proceso propio)
                                            consume:
                                              GET /api/estado
                                              GET /api/voz/transcripcion
                                              GET /api/recordatorios
                                              GET /api/tareas
```

El overlay hace polling de los mismos endpoints que ya usa `app.js` y dibuja. Es
un cliente tonto. Eso significa:

- **No toca `voice_engine.py` ni `gemini_agent.py`.** Riesgo de romper la voz:
  cero.
- Se puede desarrollar y probar **sin la app corriendo**, con respuestas falsas.
- Si crashea, Jarvis sigue funcionando.
- La ventana mini actual (Fase 10) queda **obsoleta y se puede borrar**. No
  mantener las dos: el overlay la reemplaza. Menos código, no más.

**Decisión pendiente:** hilo dentro del mismo proceso, o proceso aparte. Tk quiere
correr en el hilo principal, y pywebview también — **conviven mal**. Lo más
simple y robusto es **proceso separado**, lanzado con `subprocess` desde `ui.py`.
Encima da aislamiento gratis.

### 10.6 Que se sienta vivo: movimiento

Lo que separa "una imagen pegada en la pantalla" de "un bicho que vive ahí". En
orden de impacto por esfuerzo:

1. **Deambular (wander).** Cada N segundos, elegir un destino y desplazarse con
   `geometry('+x+y')` interpolado. Con esto solo ya parece vivo.
2. **Reposo en bordes.** Que tienda a quedarse cerca de los bordes de la pantalla
   en vez del centro — molesta menos y se ve más intencional.
3. **Evitar el cursor.** Leer la posición del mouse (`winfo_pointerxy()`) y
   apartarse si se acerca. Barato, y da una fuerte sensación de intención.
4. **Reaccionar al estado.** Quieto y lento cuando `inactivo`; se acerca al centro
   cuando `escuchando`; tiembla o vibra cuando `hablando`.
5. **Arrastrable.** Clic y arrastre para reubicarla; se queda donde la dejaste.
   Requiere que el click-through esté **apagado** (ver abajo).

**Sobre el click-through — es un interruptor, no un estado fijo.** Si está
siempre encendido, el personaje es puramente decorativo y no se le puede hacer
clic ni arrastrar. Si está siempre apagado, un cuadrado invisible te roba clics
del escritorio. La solución estándar: **click-through activado por defecto, y
desactivado solo cuando el mouse está encima de la silueta**. Se puede aproximar
con `winfo_pointerxy()` contra el rectángulo de la ventana, y ya es bastante
mejor que cualquiera de los dos extremos.

**Multi-monitor y DPI:** dos trampas conocidas de este tipo de overlay. Tk
reporta la geometría de la pantalla principal; con escalado de Windows al 125% o
150% las coordenadas se corren. Llamar
`ctypes.windll.shcore.SetProcessDpiAwareness(1)` al arrancar el overlay evita el
caso más común. Anotarlo antes de perder una tarde con eso.

### 10.7 Viñetas (bocadillos de cómic)

La idea de las viñetas encaja perfecto con la estética Watch Dogs 2 que el
proyecto ya definió (blanco y negro, trazo grueso, monoespaciada). Y hay una
oportunidad estética fuerte: **dibujar la viñeta también en ASCII**, con el
mismo lenguaje visual que la calavera.

```
 ┌──────────────────────────────┐
 │ Tenés 3 tareas sin tocar     │
 │ desde el martes. Impecable.  │
 └───────────────┬──────────────┘
                 \/
```

**Implementación:** una `Toplevel` de Tk aparte, con el mismo
`-transparentcolor`, posicionada relativa a la calavera. Que sea una ventana
propia (y no parte del mismo canvas) resuelve solo el problema de que la viñeta
tenga que crecer según el texto sin deformar al personaje.

**Cuándo aparece cada viñeta — el catálogo de "molestar":**

| Disparador | Fuente de datos | Ejemplo de tono |
|---|---|---|
| Habla por voz | `/api/voz/transcripcion` (últimas líneas de Jarvis) | lo que esté diciendo |
| Vence un recordatorio | evento del runner (hoy no expuesto, ver 7.4) | "Sacar la basura. Era hace 10 minutos." |
| Tareas pendientes viejas | `/api/tareas` con fecha | "Eso que ibas a hacer el martes sigue ahí." |
| Pregunta de cierre | inactividad + tareas del día | "¿Terminaste algo hoy o solamente movimos cosas de lugar?" |
| Ocioso | timer | comentario suelto, humor, sin acción |

**Advertencia de producto, no técnica:** "que moleste" es divertido las primeras
dos horas y se vuelve insoportable el día tres. Antes de escribir la primera
línea de esto conviene fijar tres cosas: **frecuencia máxima** (ej. no más de una
interrupción no solicitada cada 20 min), **modo silencio** (un toggle que lo
calle sin cerrarlo), y **que nunca interrumpa mientras el usuario está
escribiendo**. Sin esos tres límites, el proyecto termina desinstalado por su
propio autor. Diseñarlos desde el principio sale más barato que agregarlos
después.

### 10.8 Sonidos

Lo más lazy que funciona: **`winsound`, que es de la librería estándar y el
proyecto ya usa** para el pitido de recordatorios.

```python
winsound.PlaySound("asset.wav", winsound.SND_FILENAME | winsound.SND_ASYNC)
```

`SND_ASYNC` es lo importante: sin ese flag la reproducción bloquea.

Limitaciones: solo WAV, solo Windows, y **un sonido a la vez** (uno nuevo corta
el anterior). Para efectos cortos de UI —aparece viñeta, se cierra, vence
recordatorio, clic— alcanza y sobra. Si algún día hacen falta capas
simultáneas o mp3/ogg, ahí sí `pygame.mixer` o `simpleaudio`, no antes.

**Cuidado importante:** cualquier sonido que salga por el parlante lo capta el
micrófono y el VAD del servidor puede tomarlo como habla del usuario (es
exactamente el problema del punto 2.2). Los efectos deben ser **cortos y
apagados**, y conviene silenciarlos mientras hay sesión de voz activa — o
respetar el mismo flag de auriculares.

### 10.9 El personaje como paquete completo

Acá se unen todas las piezas de esta conversación. Un "personaje" no debería ser
solo el arte. Debería ser **todo lo que define quién es el asistente**:

```json
{
  "id": "calavera",
  "nombre": "Calavera",
  "charset": " .:░▒▓█",
  "voz": "Puck",
  "fps": 12,
  "animaciones": {
    "inactivo":    { "frames": [...], "fps": 8  },
    "hablando":    { "frames": [...], "fps": 12 },
    "escuchando":  { "frames": [...], "fps": 10 },
    "procesando":  { "frames": [...], "fps": 12 }
  },
  "vineta": { "offset_x": 60, "offset_y": -40, "ancho_max": 34 },
  "sonidos": { "aparece": "pop.wav", "vineta": "tick.wav" },
  "prompt": "…personalidad, tono y humor de este personaje…"
}
```

Con esto, "cambiar de personaje" cambia el arte, **la voz, el sonido y la
personalidad** de una sola vez. Y agregar uno nuevo sigue siendo copiar un JSON
a una carpeta.

Regla que conviene respetar: si una animación de estado falta, cae a `inactivo`.
Si `inactivo` tiene un solo frame, es una ilustración fija. Así el personaje
actual entra en este formato **sin ningún caso especial**, y alguien puede
aportar un personaje con un solo dibujo sin tener que producir cuatro clips.

### 10.10 Mejorar la animación que viene del video

Complementa la sección 6. La brecha, recordando: `convertir_ascii.py` funciona,
pero su salida nunca se generó ni se conectó, y emite un formato
(`{"fps", "frames": [[fila…]]}`) **incompatible** con el que `app.js` consume
(`{"frame": "…"}`). Unificar en el del conversor.

**Receta concreta:**

```
pip install opencv-python          # solo para la herramienta, no para la app
python Jarvis/tools/convertir_ascii.py video.mp4 salida.json --cols 120 --fps 12
```

Después re-verificar el pin de `httpx` (regla ya aprendida, `plans/ERRORES.md`).

**Mejoras al conversor que valen la pena, en orden de impacto visual:**

1. **Recortar el video antes de convertir** a un loop de 2-4 s que cicle bien. Es
   lo que más mejora el resultado y no requiere tocar código: se hace en
   cualquier editor.
2. **Normalizar el contraste** por frame (o estirar el histograma). Un mp4 con
   grises apagados produce ASCII lavado: casi todos los píxeles caen en 2-3
   caracteres de la rampa y el arte se ve plano. Es el defecto más común de este
   tipo de conversión y `frame_a_ascii()` hoy no lo hace
   (`convertir_ascii.py:36-38` mapea lineal de 0-255).
3. **Unificar la rampa con el charset del personaje.** El conversor usa
   `" .:-=+*#%@"` (`convertir_ascii.py:22`) y el arte actual usa `" .:░▒▓█"`.
   Mezclarlos hace que el ruido del estado "hablando" se vea de otro material.
   Hacer la rampa un parámetro `--charset`.
4. **Recortar los márgenes vacíos.** Si el video tiene fondo negro alrededor, se
   están guardando miles de espacios por frame y la silueta queda chica dentro de
   una caja grande — justo lo contrario de lo que se busca para el overlay.
5. **Deduplicar frames idénticos** consecutivos: en animaciones ASCII de baja
   resolución muchos frames seguidos salen iguales. Guardar índices en vez de
   repetir el arte puede recortar el archivo a la mitad sin perder nada.

**Presupuesto de tamaño** (ver tabla en 6.2): a 120 columnas, 12 fps y 3 segundos
son ~36 frames ≈ 250 KB. Cómodo. A las 400 columnas del arte actual serían
~1,4 MB por la misma animación, para un panel de 260 px de alto que no lo
aprovecha.

**Rendimiento del reproductor:** hoy `renderAscii()` (`app.js:375`) hace `join()`
sobre un array de 40.000 caracteres sueltos en cada cuadro. Con frames
pre-unidos como string y `requestAnimationFrame` con acumulador de tiempo, el
costo por cuadro es una asignación de `textContent` y nada más. En el overlay Tk
el equivalente es un `Label`/`Text` con `config(text=frame)`.

---

## 11. Área H — El prompt: respuestas directas y humor ácido

### 11.1 Diagnóstico: el problema es más grande de lo que parece

Hay **dos motores de conversación** y sus personalidades no coinciden:

**Voz** (`voice_engine.py:36-39`) — instrucción de sistema completa, textual:

```
Sos Jarvis, un asistente de voz personal. Respondé en español, de forma
breve y directa, con trato cordial hacia quien te habla.
```

**Texto** (`gemini_agent.py:172`):

```python
config = types.GenerateContentConfig(tools=[self._tools])
```

**El agente de texto no tiene NINGUNA instrucción de sistema.** Ni persona, ni
idioma, ni estilo, ni longitud. Todo lo que responde por el chat escrito es
Gemini crudo. Eso explica por sí solo buena parte de la inconsistencia de tono
entre hablarle y escribirle. Es probablemente el arreglo de mayor impacto por
menor esfuerzo de todo este documento.

Otras dos observaciones sobre el prompt de voz:

- **Es rioplatense** ("Sos", "Respondé"). Si el usuario habla español
  colombiano, el asistente le está contestando en otro dialecto. Puede ser
  intencional; si no lo es, corregirlo cambia bastante la sensación.
- **No dice nada sobre no repetir la pregunta**, que es justamente la queja.

### 11.2 Por qué repite la pregunta antes de responder

Tres causas que se suman:

1. **Nada se lo prohíbe.** Es un comportamiento por defecto de los modelos
   conversacionales: reformulan para confirmar que entendieron. En texto se
   tolera; **en voz es insoportable**, porque el usuario tiene que escuchar toda
   la reformulación antes de la respuesta. La literatura de agentes de voz lo
   marca como uno de los errores clásicos: *no repetir frases exactas del
   usuario*.
2. **"breve y directa" es demasiado vago.** Los modelos responden mucho mejor a
   restricciones verificables ("máximo dos frases", "empezá por la respuesta")
   que a adjetivos.
3. **Reaseguro por audio incierto.** Si el reconocimiento no viene limpio (ver
   toda la sección 3), el modelo tiende a repetir lo que creyó oír. O sea: parte
   de este síntoma se arregla mejorando el audio, no el prompt.

### 11.3 Estructura recomendada

Las guías de prompts para agentes de voz coinciden en cuatro pilares:
**Persona** (cómo suena) · **Contexto** (qué sabe de entrada) · **Reglas** (qué
debe y qué no debe hacer) · **Conocimiento** (de dónde saca las respuestas).

El prompt actual solo cubre Persona, y a medias.

### 11.4 Borrador para discutir (NO implementado)

Para el personaje "calavera", pensado para voz y reutilizable en texto:

```
IDENTIDAD
Sos Jarvis. Una calavera que vive en el escritorio de [nombre] y le hace de
asistente. Estás muerto, no tenés nada que perder, y eso se te nota al hablar.

CÓMO RESPONDÉS
- Empezá SIEMPRE por la respuesta. Nunca repitas ni reformules lo que te
  preguntaron.
- Máximo dos frases, salvo que te pidan detalle explícitamente.
- Nada de preámbulos: prohibido "Claro", "Por supuesto", "Buena pregunta",
  "Déjame ver", "Entiendo que querés saber".
- Si ejecutás una acción, confirmala en pocas palabras y callate.
- Si no sabés algo, decilo en una frase. No inventes.

HUMOR
- Ácido y negro, seco, nunca festivo. Ironía por lo bajo, no chiste armado.
- El remate va DESPUÉS de la información útil, nunca en lugar de ella.
- Como mucho un comentario por respuesta. Dos ya cansa.
- El humor sale del contexto concreto de lo que se te preguntó: la tarea que
  sigue sin hacerse, la hora que es, el recordatorio que se ignoró tres veces.
  Humor genérico y pegado no sirve.
- Te burlás de la situación y de vos mismo. Nunca de la persona por lo que es.
  Sin comentarios sobre su cuerpo, su capacidad ni su vida personal. Y si
  parece que lo está pasando mal de verdad, bajás el chiste y respondés
  derecho — leer el momento es parte del personaje.

VOZ
Estás hablando en voz alta. Nada de listas, viñetas, markdown ni emojis. Números
y fechas en palabras cuando se lean mejor. Frases cortas.
```

Sobre el pedido de humor **basado en el contexto de lo que se pregunta**: la
condición para que eso funcione es que el modelo tenga contexto real. Inyectar en
la instrucción de sistema, en cada arranque de sesión, la hora, la cantidad de
tareas pendientes y cuáles llevan más días sin tocarse convierte el humor
genérico en humor específico. Es la diferencia entre "qué productivo" y "eso que
ibas a hacer el martes cumple una semana". Los datos ya están en `tareas.json` y
`recordatorios.json`; solo hay que pasarlos.

### 11.5 Cosas a probar y cosas a vigilar

**A favor:** la Live API tiene **affective dialog** (ver 7.3) — el modelo adapta
tono a la expresión del usuario. Combinado con un personaje sarcástico, es
justamente lo que evita que el humor caiga mal en un mal momento.

**A vigilar:** "humor negro" empuja contra los filtros de seguridad del modelo.
Puede pasar que rechace responder, o que se ablande solo y vuelva al tono neutro
a los pocos turnos. Es un comportamiento esperable, no un bug del código. Si
molesta, hay dos palancas: reformular el prompt hacia "ironía seca" en vez de
"humor negro" (funciona mejor de lo que parece), y revisar `safety_settings` en
la configuración de generación. Conviene medirlo con conversaciones reales antes
de dar el prompt por bueno.

**Sobre la persistencia del tono:** en conversaciones largas los modelos derivan
hacia el registro neutro. Si pasa, el remedio no es un prompt más largo sino
reforzar la identidad en pocas líneas y ponerlas al final de la instrucción de
sistema, que es la posición que más peso conserva.

**Un punto que decidir antes de escribir el prompt final:** ¿el humor ácido
aplica también cuando reporta un recordatorio importante? Un recordatorio médico
o una reunión con un chiste encima puede jugar en contra de la función del
recordatorio. Vale la pena que el prompt distinga entre "charla" y "aviso", y que
en los avisos sea seco y claro primero.

---

## 12. Actualización del flujo de trabajo (reemplaza la sección 9 en lo que respecta a UI)

Las tandas 1 y 2 de la sección 9 no cambian. La tanda 3 se reemplaza por esto,
porque el overlay cambia el orden natural de las cosas:

| Fase | Qué | Nota |
|---|---|---|
| **17** | **Prompt e identidad**: instrucción de sistema para `gemini_agent` (hoy no tiene ninguna), reescribir la de voz con la estructura de 11.3, humor ácido, prohibición de repetir la pregunta | Lo más barato y lo que más se nota. **Va primero** |
| **18** | **Formato único de personaje** (10.9) + `/api/personajes` + selector. Migrar la calavera actual. Incluye `prompt` y `voz` en el paquete | Habilita todo lo demás |
| **19** | **Animación real**: correr el conversor sobre el mp4 (120 cols, 12 fps, loop corto), mejoras de 10.10, reproductor multi-frame | |
| **20** | **Overlay flotante `tkinter`**: silueta con `-transparentcolor`, topmost, proceso aparte, consume `/api/estado`. Sin movimiento todavía. **Borrar la ventana mini de la Fase 10** | El salto grande. Sin dependencias nuevas |
| **21** | **Vida**: deambular, evitar el cursor, arrastrable, click-through condicional, DPI awareness | |
| **22** | **Viñetas + sonidos**: `Toplevel` con bocadillo ASCII, `winsound`, y los tres límites de 10.7 (frecuencia máxima, modo silencio, no interrumpir mientras se escribe) | Los límites van en la MISMA fase, no después |
| **23** | `proactive_audio` + `affective_dialog` (`v1alpha`) | |

Las tandas de recordatorios (fases 20-22 originales) se corren detrás y se
renumeran.

**Dependencia importante que conviene no romper:** la fase 20 (overlay) necesita
el formato de personaje de la 18, porque el overlay lee el arte desde ahí. Y la
22 (viñetas) necesita que los recordatorios expongan eventos (punto 7.4). Si se
quiere adelantar el overlay, se puede hacer contra el arte actual y refactorizar
después — pero es trabajo duplicado.

---

## 13. Área I — Cambio de dirección: sprites 2D (GIF) en vez de ASCII

Decisión del usuario, posterior a las secciones 10 y 12:

> "cambiar las imágenes por varios GIF según cada estado o situación… me lo
> imagino una calavera en 2D con diversas animaciones. Y sí me gustaría mucho
> lograr lo de las viñetas."

Esto **simplifica** el proyecto en vez de complicarlo, y conviene decirlo claro:
la conversión mp4 → ASCII (sección 6 y 10.10) era la parte más frágil y más
artesanal de todo el plan. Si el personaje va a ser un sprite 2D animado, esa
tubería entera **desaparece**. Menos código, no más.

### 13.1 Lo que se cae del plan anterior

| Se cae | Motivo |
|---|---|
| `Jarvis/tools/convertir_ascii.py` | Ya no hace falta convertir video a ASCII |
| Las mejoras del conversor (10.10) | idem |
| `skull_frame.json` y su formato | Reemplazado por sprites |
| El ruido de caracteres de `app.js:422-431` | No aplica a un sprite |
| El presupuesto de tamaño ASCII (6.2) | Reemplazado por el de imágenes |
| `opencv-python` como dependencia de desarrollo | Ya no hace falta |

**Lo que sobrevive intacto** de la investigación anterior, y es lo importante:
todo el análisis del overlay (10.2 a 10.8), el spike de ventanas transparentes,
la arquitectura de "el overlay es un cliente tonto que hace polling", el paquete
de personaje (10.9), las viñetas y el prompt (sección 11).

### 13.2 Spike 2 — formatos de imagen verificados en esta máquina

Se corrió una segunda prueba real (scratchpad, nada tocado en el repo):

| Capacidad | Resultado |
|---|---|
| Versión de Tk | **8.6.15** |
| GIF multi-frame: `PhotoImage(file=..., format="gif -index N")` | **soportado** |
| PNG con canal alfa nativo | **soportado** |
| Cargar un PNG real del repo (884×497) | **OK** |
| Reducir sin Pillow: `img.subsample(n)` | **OK** (solo factores enteros) |
| 60 reposicionamientos de ventana + `update()` | **429 ms ≈ 7 ms cada uno** |

Dos conclusiones fuertes:

1. **No hace falta Pillow.** Tk 8.6 lee GIF animado y PNG con alfa de fábrica.
   (Dato: Pillow **no** está instalado en el Python global con el que corre la
   app; sí aparece en el `.venv` que no se usa. Ver punto 8.1 — el entorno
   dividido vuelve a morder.)
2. **El movimiento va a ser fluido.** 7 ms por cuadro deja muchísimo margen
   dentro del presupuesto de 16 ms de 60 fps. Deambular, rebotar y esquivar el
   cursor no van a trabarse.

### 13.3 El punto crítico: el halo (leer antes de encargar el arte)

Es lo único que puede arruinar el resultado, y es una decisión de **arte**, no de
código. Vale la pena entenderlo bien antes de dibujar nada.

La transparencia de la ventana es por **color clave** (`-transparentcolor`): el
sistema vuelve invisible **un color exacto**. Es binario: un píxel es 100 %
visible o 100 % invisible, no hay medias tintas.

Ahora bien, qué pasa con cada formato:

| Formato | Bordes | Con color clave |
|---|---|---|
| **GIF** | 1 bit de transparencia: cada píxel es opaco o transparente, sin medias tintas | **Limpio.** Es exactamente el mismo modelo |
| **PNG con alfa suave** | Bordes semitransparentes, sombras, brillos | **Halo.** Tk mezcla el borde contra el fondo del widget (el color clave), y esos píxeles mezclados ya no son el color exacto → queda un contorno fantasma |
| **PNG con alfa dura** (todo 0 o 255) | Sin medias tintas | **Limpio**, igual que GIF |

**Regla de arte, entonces:** bordes duros. Nada de sombras difuminadas, glows,
degradados hacia el fondo ni antialiasing en el contorno exterior.

Y acá está lo lindo: **eso es exactamente la estética Watch Dogs 2 que el
proyecto ya definió** — trazo blanco grueso sobre negro, estilo cómic,
monocromático. Un contorno duro y marcado no es un sacrificio, es el estilo. Las
dos restricciones apuntan al mismo lugar.

(Si algún día se quisiera alfa real con bordes suaves, la salida es
`UpdateLayeredWindow` vía ctypes o migrar el overlay a PyQt6. Es bastante más
trabajo y **no hace falta** para este estilo. Anotado por si cambia el criterio,
no como pendiente.)

### 13.4 Qué formato usar

| Opción | Pros | Contras | Veredicto |
|---|---|---|---|
| **GIF animado, uno por estado** | Un archivo por animación, se previsualiza en cualquier lado, Tk lo lee nativo, transparencia binaria = cero halo | 256 colores (irrelevante en blanco y negro) | **Recomendado** |
| PNG numerados (`hablando_00.png`…) | Control total cuadro a cuadro, fácil de editar uno suelto | Muchos archivos | Buena alternativa |
| Spritesheet (una PNG con la grilla) | Un solo archivo, 1 carga | Recortar sin Pillow es incómodo | No, sin Pillow |
| APNG / WebP animado | Alfa real | **Tk no los lee** | Descartado |

**Recomendación: GIF animado, uno por estado.** Para blanco y negro con bordes
duros, las limitaciones del GIF no cuestan nada, y es el formato con el que
cualquier herramienta de animación exporta sin fricción.

**Cómo se lee un GIF animado con tkinter puro** (sin dependencias):

```python
frames = []
i = 0
while True:
    try:
        frames.append(tk.PhotoImage(file=ruta, format=f"gif -index {i}"))
    except tk.TclError:
        break          # se acabaron los cuadros
    i += 1
```

Dos trampas conocidas, las dos ya verificadas como manejables:

- **Hay que guardar una referencia a cada `PhotoImage`.** Si el recolector de
  basura se las lleva, la imagen desaparece sin ningún error. Es el bug más
  clásico de imágenes en tkinter. Guardar la lista `frames` en un atributo, no en
  una variable local.
- **El GIF trae su propio timing por cuadro y Tk no lo expone.** Hay que fijar el
  ritmo a mano (`after(ms)`) o declararlo en el JSON del personaje. Mejor lo
  segundo: queda explícito y se puede variar por estado.

### 13.5 Catálogo de animaciones — "según cada estado o situación"

El usuario pidió animaciones por estado **y por situación**. Son dos ejes
distintos y conviene separarlos, porque el costo de producción es muy distinto.

**Eje 1 — Estados (los 4 que el backend ya reporta en `/api/estado`).** Son de
reproducción continua, en bucle:

| Estado | Qué hace la calavera | Prioridad |
|---|---|---|
| `inactivo` | respira, parpadea de vez en cuando, mira alrededor | **Imprescindible** |
| `escuchando` | atenta, se inclina hacia adelante, orejas/antena arriba | **Imprescindible** |
| `hablando` | mandíbula moviéndose en bucle | **Imprescindible** |
| `procesando` | piensa, gira, engranajes, ojos que dan vueltas | **Imprescindible** |

Con estos cuatro el personaje ya está vivo. **Son el mínimo viable.**

**Eje 2 — Situaciones (eventos puntuales).** Se reproducen **una vez** y vuelven
al estado que corresponda:

| Situación | Disparador | Prioridad |
|---|---|---|
| aparece / se despierta | overlay arranca | Alta |
| se va a dormir | overlay se oculta | Alta |
| aviso de recordatorio | vence un recordatorio | Alta |
| burla / sarcasmo | tarea vieja sin hacer | Media |
| celebración | tarea completada | Media |
| lo agarran y arrastran | click y drag | Media |
| sorpresa | clic encima | Baja |
| error / no entendí | fallo de tool | Baja |

**Regla que abarata todo esto:** si falta una animación de situación, se cae al
estado correspondiente sin ningún caso especial. Así el personaje se puede
publicar con las 4 de estado, y las situaciones se agregan de a una cuando haya
ganas de dibujarlas. **Nunca bloquear el overlay por falta de arte.**

Presupuesto realista: 4 animaciones × 8-12 cuadros a 200×200 px ≈ **menos de
1 MB en total**. Nada. El costo real acá es dibujar, no almacenar.

### 13.6 El paquete de personaje, versión sprites

Reemplaza el JSON de 10.9:

```json
{
  "id": "calavera",
  "nombre": "Calavera",
  "voz": "Puck",
  "color_clave": "#ff00fe",
  "tamano": [200, 200],
  "estados": {
    "inactivo":   { "gif": "inactivo.gif",   "fps": 8  },
    "escuchando": { "gif": "escuchando.gif", "fps": 10 },
    "hablando":   { "gif": "hablando.gif",   "fps": 12 },
    "procesando": { "gif": "procesando.gif", "fps": 12 }
  },
  "situaciones": {
    "aparece":     { "gif": "aparece.gif",  "fps": 12, "loop": false },
    "recordatorio":{ "gif": "aviso.gif",    "fps": 12, "loop": false }
  },
  "vineta": { "ancla": [140, 30], "ancho_max": 34 },
  "sonidos": { "aparece": "pop.wav", "vineta": "tick.wav" },
  "prompt": "…personalidad, tono y humor de este personaje…"
}
```

Estructura de carpeta:

```
Jarvis/assets/personajes/calavera/
    personaje.json
    inactivo.gif  escuchando.gif  hablando.gif  procesando.gif
    aparece.gif   aviso.gif
    pop.wav       tick.wav
```

Agregar un personaje = copiar una carpeta. Sigue siendo la regla.

`color_clave` va por personaje a propósito: el color clave debe ser un color que
**no aparezca en el arte**, y eso depende del arte. Magenta puro (`#ff00fe`) es
el default seguro para una paleta blanco y negro.

`ancla` es dónde nace la cola de la viñeta, en coordenadas del sprite — porque
depende de dónde tenga la boca cada personaje.

### 13.7 De dónde sale el arte

El punto que **no** es técnico y que va a decidir el resultado. Opciones, con
honestidad sobre cada una:

1. **Dibujarlo a mano** (Aseprite, Krita, Piskel gratis en el navegador). Aseprite
   es el estándar para sprites y exporta GIF directo. Control total, encaja con
   el estilo cómic, y una calavera monocroma de 200×200 es de las cosas más
   accesibles de animar para alguien sin experiencia previa.
2. **Generar con IA + limpiar.** Sale rápido, pero el problema es la
   **consistencia entre cuadros**: los generadores producen imágenes parecidas,
   no cuadros de la misma animación. Sirve mejor para sacar **una** pose base por
   estado y animar variaciones simples encima (mandíbula, parpadeo).
3. **Partir del mp4 que ya tenés.** Recortarlo, umbralizarlo a blanco y negro
   puro (que además da los bordes duros que hacen falta) y exportar GIF. Cero
   dibujo. Es el camino más corto a "algo que se mueve en pantalla" — sirve muy
   bien como *placeholder* para desarrollar el overlay mientras se produce el
   arte definitivo.
4. **Sprites libres** de itch.io / OpenGameArt para prototipar.

**Recomendación de secuencia:** empezar con 3 para tener algo moviéndose y
desbloquear el desarrollo del overlay, y reemplazar por 1 sin tocar código —
justamente para eso el personaje es una carpeta con un JSON.

Nota sobre la umbralización del mp4: es lo mismo que hacía `convertir_ascii.py`
en su primer paso (pasar a gris), pero cortando en blanco/negro puro en vez de
mapear a caracteres. Cualquier editor de video o un script de 15 líneas lo hace.

### 13.8 ¿Y el panel ASCII de la ventana principal?

Decisión pendiente que conviene tomar explícitamente, porque hoy hay **dos
lugares** donde se muestra el personaje:

| Opción | Qué implica |
|---|---|
| **A. Sprite en los dos lados** | Coherencia total. El `<pre>` de `app.js` pasa a ser un `<img>`. El navegador reproduce el GIF solo, sin código de animación. Se borra bastante JS |
| B. ASCII en la ventana, sprite en el overlay | Dos personajes distintos para mantener y dos formatos de arte por personaje |

**Recomendación: A.** Un `<img src="…/hablando.gif">` que cambia de `src` según
el estado reemplaza `cargarAsciiSkull`, `renderAscii`, `ruidoCaracteres`,
`ajustarEscalaAscii` y el `ResizeObserver` — unas 70 líneas de `app.js` que se
borran, y el navegador anima el GIF gratis. El glitch CSS puede quedarse, es
independiente del contenido y aporta a la estética.

Contra: se pierde el arte ASCII, que tiene su encanto y ya está hecho. Si pesa,
la salida barata es dejarlo como **un personaje más** dentro del selector
(`"tipo": "ascii"` vs `"tipo": "sprite"`) — pero eso obliga al overlay a saber
dibujar las dos cosas. **No vale la pena a menos que el usuario lo pida.**

### 13.9 Las viñetas, ahora que hay sprite

Nada de lo dicho en 10.7 cambia; el sprite lo mejora en un punto concreto:
**ahora hay un ancla real** (`vineta.ancla`) para que la cola del bocadillo salga
de la boca del personaje y lo siga cuando se mueve.

Sigue siendo una `Toplevel` de Tk aparte con el mismo color clave, reposicionada
junto con la ventana del personaje. El bocadillo puede dibujarse en un `Canvas`
(rectángulo + polígono para la cola + texto) — **sin necesidad de arte**, lo cual
lo desacopla completamente de la producción de los GIF. Buena noticia: **las
viñetas se pueden construir antes de que exista un solo sprite.**

Y siguen valiendo los tres límites innegociables de 10.7: frecuencia máxima, modo
silencio, y no interrumpir mientras el usuario escribe.

### 13.10 Roadmap actualizado (reemplaza las fases 18-22 de la sección 12)

| Fase | Qué | Cambio |
|---|---|---|
| **17** | Prompt e identidad (sección 11) | **sin cambios**, sigue primero |
| **18** | Paquete de personaje **con sprites** (13.6) + `/api/personajes` + selector | Reemplaza el formato ASCII |
| **19** | **Overlay `tkinter`**: silueta con color clave, GIF por estado, topmost, proceso aparte, consume `/api/estado`. Borrar la ventana mini de Fase 10 | Antes era la 20; **sube**, porque ya no depende del conversor ASCII |
| **20** | Vida: deambular, esquivar el cursor, arrastrable, click-through condicional, DPI awareness | igual |
| **21** | Viñetas + sonidos + los tres límites | igual. **Se puede adelantar**: no depende del arte |
| **22** | Animaciones de situación (13.5, eje 2) | nueva, incremental |
| **23** | `proactive_audio` + `affective_dialog` | igual |
| ~~conversor ASCII~~ | — | **eliminada** |

**Camino crítico ahora:** el arte. Todo lo demás está desbloqueado y verificado.
Por eso conviene arrancar con el placeholder del punto 13.7 opción 3: permite
construir las fases 19, 20 y 21 completas mientras el arte definitivo se produce
en paralelo, sin que una cosa espere a la otra.

---

## 14. Fuentes

Documentación oficial:

- [Live API — guía de sesión y VAD](https://ai.google.dev/gemini-api/docs/live-guide)
- [Live API — uso de herramientas (async function calling, scheduling)](https://ai.google.dev/gemini-api/docs/live-tools)
- [Live API — guía de capacidades (modelos, proactive audio, affective dialog)](https://ai.google.dev/gemini-api/docs/live-api/capabilities)
- [Live API — gestión de sesiones](https://ai.google.dev/gemini-api/docs/live-session)
- [Live API — referencia WebSockets](https://ai.google.dev/api/live)
- [Vertex AI — mejores prácticas con la Live API](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/live-api/best-practices)
- [Vertex AI — troubleshooting de la Live API](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/live-api/troubleshooting)
- [Gemini 2.5 Flash con Live API](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/2-5-flash-live-api)

Problemas reportados por la comunidad (transcripción):

- [Input transcription in gemini live api is very weird](https://discuss.ai.google.dev/t/input-transcription-in-gemini-live-api-is-very-weird/112644)
- [input_audio_transcription returns incorrect text while model correctly processes audio](https://discuss.ai.google.dev/t/gemini-live-api-input-audio-transcription-returns-incorrect-text-while-model-correctly-processes-audio/128300)
- [Delays or Missing input_audio_transcription Events](https://discuss.ai.google.dev/t/gemini-live-api-delays-or-missing-input-audio-transcription-events/110732)
- [Transcription sometimes shows incorrect language (livekit/agents#3551)](https://github.com/livekit/agents/issues/3551)
- [Session resumption inestable tras audio+video (python-genai#2290)](https://github.com/googleapis/python-genai/issues/2290)

Navegador:

- [Chromium — Creating and Using Profiles](https://www.chromium.org/developers/creating-and-using-profiles/)
- [How to Launch Chrome Using a Profile from CLI](https://www.ianwootten.co.uk/2023/05/18/how-to-launch-chrome-using-a-profile-from-cli/)
- [Python — módulo webbrowser](https://docs.python.org/3/library/webbrowser.html)

Ventanas transparentes / desktop pets:

- [pywebview #745 — Window Webview2 transparency support](https://github.com/r0x0r/pywebview/issues/745)
- [pywebview #1200 — Windows System `transparent=True`](https://github.com/r0x0r/pywebview/issues/1200)
- [pywebview #1271 — transparencia y penetración del mouse](https://github.com/r0x0r/pywebview/issues/1271)
- [pywebview #488 — Support for Window Transparency](https://github.com/r0x0r/pywebview/issues/488)
- [pywebview — API reference](https://pywebview.flowrl.com/api/)
- [jfd02/tkinter-transparent-window — ejemplo de referencia](https://github.com/jfd02/tkinter-transparent-window/blob/main/main.py)
- [Click-through tkinter windows (WS_EX_LAYERED / WS_EX_TRANSPARENT)](https://johnnn.tech/q/click-through-tkinter-windows/)
- [Shimeji-ee — desktop pet de referencia](https://kilkakon.com/shimeji/)

Prompting de agentes de voz:

- [Vapi — Voice AI Prompting Guide](https://docs.vapi.ai/prompting-guide)
- [Cómo escribir un system prompt para un agente de voz (2026)](https://www.famulor.io/blog/how-to-write-an-ai-voice-agent-system-prompt-in-2026)
- [System instructions y persona prompts para Gemini en Vertex AI](https://oneuptime.com/blog/post/2026-02-17-how-to-configure-system-instructions-and-persona-prompts-for-gemini-on-vertex-ai/view)
- [CloudTalk — VoiceAgent prompt best practices](https://help.cloudtalk.io/en/articles/11058815-voiceagent-prompt-best-practices)

Fuentes internas del repo: `plans/ERRORES.md`, `plans/phase-06-voz-gemini-live.md`,
`plans/phase-09-ascii-panel.md`, `plans/phase-10-pip-overlay.md`, y lectura
directa del código citado.

Imágenes y sprites en tkinter:

- [Tk `photo` — formatos e `-index` para GIF multi-cuadro](https://www.tcl.tk/man/tcl8.6/TkCmd/photo.html)
- [Transparencia de imágenes en Tkinter (discusión)](https://www.daniweb.com/programming/software-development/threads/352722/transparent-image-python-tkinter)
- [Aseprite — editor de sprites, exporta GIF](https://www.aseprite.org/)
- [Piskel — editor de sprites gratuito en el navegador](https://www.piskelapp.com/)

**Verificación propia:** los dos spikes se ejecutaron de verdad en esta máquina
(Windows 11, Tk 8.6.15) con scripts descartables en el scratchpad de la sesión.

- *Spike 1* (sección 10.3): `overrideredirect`, `-topmost`, `-transparentcolor`,
  `-alpha`, click-through vía `WS_EX_LAYERED|WS_EX_TRANSPARENT` con `ctypes`, y
  reposicionamiento — todo OK.
- *Spike 2* (sección 13.2): soporte de `gif -index N` y `png` con alfa, carga de
  un PNG real de 884×497, `subsample()`, y 60 reposicionamientos con `update()`
  en 429 ms (~7 ms por cuadro).

No se agregó ni se modificó ningún archivo del proyecto para hacerlos.
