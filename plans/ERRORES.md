# Registro de errores y aprendizajes — Jarvis

Bitácora de fallos reales encontrados durante la ejecución de las fases del
plan (`plans/phase-NN-*.md`), su causa raíz, cómo se resolvieron, y la
estrategia concreta para no repetirlos. No es un changelog de features —
es específicamente para errores, decisiones que salieron mal, y supuestos
que resultaron falsos.

## Cómo usar este documento

**Antes de implementar una fase** (`jarvis-builder` / `jarvis-ui-builder`):
leer la sección "Reglas aprendidas" de abajo completa — son mini-reglas ya
validadas por errores reales pasados, evitan repetir el mismo tropiezo.

**Antes de revisar una fase** (`jarvis-reviewer`): chequear si algún
hallazgo de la revisión actual coincide con una entrada ya registrada acá
— si es la MISMA clase de error que ya pasó antes, marcarlo como
"regresión de error conocido" en el reporte, es más grave que un fallo
nuevo (significa que la regla aprendida no se está aplicando).

**Al encontrar un error real** (cualquier agente con permiso de escritura):
agregar una entrada nueva al final de "Historial de entradas" con el
formato de abajo, y si el error revela una regla generalizable, agregar
una línea nueva a "Reglas aprendidas" (arriba, para que la lea el próximo
agente antes de empezar). No registrar acá errores triviales de sintaxis
que se corrigieron al toque sin causar ninguna decisión de diseño — es
para errores que costaron tiempo, llevaron por un camino equivocado, o
revelaron un supuesto falso sobre una librería/API externa.

---

## Reglas aprendidas

- **Antes de marcar "fuera de alcance violado" por un archivo modificado,
  confirmar si el diff es anterior a la fase actual.** `git diff` contra
  `HEAD` no distingue cambios sin commitear que ya existían ANTES de que
  arrancara el plan de los que introdujo el builder recién. Chequear con
  `git log -1 -- <archivo>` y, si hay dudas, preguntar al usuario antes de
  reportarlo como FAIL o de revertir nada — puede ser trabajo en progreso
  del usuario ajeno al plan. Ver entrada 2026-07-26 Fase 01.
- **Al portar un módulo a una carpeta con distinta profundidad, recalcular
  a mano cuántos `.parent` hacen falta** — no copiar la fórmula
  `Path(__file__).resolve().parent.parent` de otro archivo del proyecto
  (p. ej. `config.py`) sin fijarse en cuántos niveles de carpeta separan a
  cada archivo de la raíz. Verificar SIEMPRE con un `print()`/check rápido
  (ej. `python -c "from app.actions.X import RUTA; print(RUTA)"`) que la
  ruta resultante es la esperada antes de dar la fase por terminada. Ver
  entrada 2026-07-26 Fase 02.
- **Un self-check de una función que produce audio/voz debe llamarla con un
  texto real no vacío, no solo con `""`.** Un self-check que solo prueba el
  caso vacío (que retorna antes de tocar el motor real) pasa siempre y da
  falsa confianza — nunca ejercitó el motor de verdad. Confirmar con
  audio real (o al menos sin excepción) antes de dar por probada una
  función de voz. Ver entrada 2026-07-26 Fase 03 (segunda entrada, TTS).
- **Antes de dar por buena una librería externa nueva agregada a
  `requirements.txt`, probarla con una llamada real, no asumir que "instala
  y listo" porque el plan la menciona.** Paquetes poco mantenidos (última
  release años atrás) pueden depender de una versión vieja de una librería
  transitiva (ej. una firma de función que cambió). Si falla, buscar si un
  pin de la dependencia transitiva lo arregla antes de asumir que hay que
  escribir el fallback completo. Ver entrada 2026-07-26 Fase 04
  (`youtube-search-python` + `httpx`).
- **Un self-check que espera un evento de un runner con intervalo de polling
  fijo (`while True: ...; time.sleep(N)`) debe esperar, desde la CREACIÓN
  del evento, al menos (tiempo hasta que el evento vence) + N + margen** —
  no el tiempo del evento a secas. El primer chequeo del loop corre casi
  inmediatamente al arrancar el hilo (antes de que venza el evento), así
  que recién se detecta en el SEGUNDO chequeo, que ocurre hasta N segundos
  después de que el evento ya venció. Esperar exactamente el tiempo del
  evento desde su creación es una carrera que puede fallar de forma
  intermitente. Ver entrada 2026-07-26 Fase 03 (evento a 5s + intervalo de
  polling de 10s → esperar 16s, no 10s).
- **Antes de exponer una función a function-calling de un LLM, auditar
  TODOS sus caminos internos hasta `subprocess`/`shell=True`, no solo el
  camino feliz.** Un "último recurso" que cae a texto no filtrado (sin
  pasar por una allowlist) puede ser seguro hoy por casualidad de cómo
  quotea `cmd.exe`, pero es una base frágil en cuanto el input deja de ser
  el usuario tecleando y pasa a ser la salida de un modelo. Ver entrada
  2026-07-26 Fase 04 (`open_app.py`, paso 6 de `_try_start_command`).
- **Instalar una dependencia nueva puede desactualizar silenciosamente un
  pin ya puesto en `requirements.txt` para otra dependencia transitiva
  compartida.** `pip install <paquete nuevo>` resuelve el árbol completo de
  nuevo y puede subir una versión que otro paquete ya fijado necesitaba
  abajo. Después de agregar cualquier dependencia nueva, re-correr los
  self-checks existentes de librerías que tengan un pin documentado (no
  asumir que un pin viejo sigue vigente). Ver entrada 2026-07-26 Fase 05
  (`google-genai` subió `httpx` a 0.28.1 y rompió `youtube-search-python`
  de nuevo).
- **Que un modelo aparezca en `client.models.list()` no garantiza que
  `generate_content()` funcione con esa cuenta/API key.** Un modelo puede
  seguir listado (metadata no purgada) pero devolver 404
  "no longer available to new users" al usarlo de verdad. Confirmar el
  modelo con una llamada real a `generate_content`, no solo con el
  listado. Ver entrada 2026-07-26 Fase 05 (`gemini-2.5-flash` listado pero
  404; `gemini-flash-latest` sí funciona).
- **El grounding con `google_search` tiene una cuota separada de la cuota
  general de `generateContent`, casi nula en cuentas sin billing
  habilitado.** Una API key que responde bien a `generate_content` normal
  puede devolver `429 RESOURCE_EXHAUSTED` específicamente al usar la tool
  `google_search`, sin que sea un bug de nombre de tool ni de código. No
  hay que "arreglarlo" reintentando nombres de tool distintos: es una
  restricción de cuenta/billing de Google, se resuelve habilitando billing
  en la consola de Google Cloud/AI Studio, no en el código. Ver entrada
  2026-07-26 Fase 05 (`buscar_web`).
- **El checkbox `- [x] Fase NN` en `plans/README.md` NUNCA lo marca el
  builder ni es motivo de RECHAZADA del reviewer.** Lo marca la skill
  `jarvis-phase` después del veredicto APROBADA — es el único paso del
  "Entregable final" de cada fase que no le corresponde auditar al
  reviewer. Pasó dos veces (fases 01 y 06) que el reviewer lo marcó como
  FAIL antes de que esto quedara explícito en las instrucciones del
  agente `jarvis-reviewer`. Ver entrada 2026-07-26 Fase 06.
- **En un stream de audio bidireccional (Live API), para silenciar el mic
  mandar silencio (bytes en cero) del mismo tamaño, no cortar el envío.**
  Mantener el streaming continuo es lo prolijo. OJO: esta regla se escribió
  creyendo que cortar el envío era la causa de "responde una vez y después
  nunca más" — **ese diagnóstico era incorrecto**, la causa real era el
  generador `session.receive()` agotándose por turno (ver regla siguiente).
  Ver entrada 2026-07-26 Fase 06 (segunda entrada, eco/VAD).
- **`session.receive()` de la Live API es un generador POR TURNO, no por
  sesión: hay que volver a pedirlo en un `while` externo.** Se agota
  cuando el modelo termina de responder. Un `async for msg in
  session.receive():` suelto lee UN turno y termina — la sesión queda viva
  pero sorda, sin ningún error. Síntoma: "responde una vez y después se
  queda escuchando para siempre". Ver entrada 2026-07-26 Fase 06 (tercera
  entrada).
- **Una `asyncio.Task` que muere por excepción no avisa nada hasta que
  alguien la awaitea.** Si el motor depende de tasks de fondo, chequear
  `task.done()` / `task.exception()` periódicamente y loguearlo — si no,
  un crash se ve exactamente igual que "está pensando". Ver entrada
  2026-07-26 Fase 06 (tercera entrada).
- **Nunca hacer una escritura bloqueante de audio (`stream.write()`)
  dentro del mismo task que lee los mensajes del servidor.** Bloquea la
  lectura durante toda la reproducción. La reproducción va en un hilo
  aparte con su propia cola. Ver entrada 2026-07-26 Fase 06 (tercera
  entrada).
- **Los índices de `navigator.mediaDevices.enumerateDevices()` NO son los
  índices de PortAudio/`sounddevice`.** Poblar un selector de mic/altavoz
  desde el navegador y guardar ese índice para usarlo en Python manda el
  audio a otro dispositivo — puede ser uno que no suena, sin ningún error.
  Listar dispositivos SIEMPRE desde el backend
  (`sounddevice.query_devices()`). Ver entrada 2026-07-26 Fase 08/09
  (dispositivos de audio).
- **No configurar `realtime_input_config` (VAD explícito) sin probarlo de
  punta a punta.** Con esa config puesta, el servidor dejó de mandar
  ABSOLUTAMENTE TODO (ni una transcripción, con el mic enviando audio
  normal), tanto con sensibilidad LOW como HIGH. El VAD automático por
  defecto funciona. Ver entrada 2026-07-26 Fase 06 (cuarta entrada).
- **`config._check()` escribe sobre el `datos/settings.json` REAL, no uno de
  prueba aislado.** Re-correrlo (incluso solo para confirmar que una clave
  nueva de `DEFAULTS` no rompió nada) pisa preferencias reales del usuario
  con los valores de prueba del check (deja `voice` en `"Kore"`). Antes de
  correr `python -m app.config`, anotar el valor real de los campos que el
  check toca (`voice`) para poder restaurarlo después, o evitar correrlo
  sobre el `settings.json` de producción. Ver entrada 2026-07-28 Fase 11.
- **El campo `behavior` de `types.FunctionDeclaration` (`NON_BLOCKING`) solo
  lo acepta `BidiGenerateContent` (sesión Live) — `generate_content` normal
  responde `400 INVALID_ARGUMENT` si lo recibe, aunque el campo exista en el
  SDK y no tire error al construir el objeto en Python.** Que
  `types.FunctionDeclaration(..., behavior=...)` no tire excepción al
  instanciarse NO significa que la API lo acepte en cualquier método — hay
  que probarlo con una llamada real al método específico que se va a usar,
  no asumir que "si el SDK lo permite, el server también". Si una
  declaración de tools se comparte entre un agente sync (`generate_content`)
  y uno Live, construir dos variantes (una con el campo, otra sin) en vez de
  una sola compartida. Ver entrada 2026-07-28 Fase 12.

---

## Historial de entradas

## [2026-07-26] Fase 01 — reviewer marcó FAIL por diff preexistente en `Jarvis/jarvis.py`

- **Qué pasó:** `jarvis-reviewer` marcó la fase como RECHAZADA porque
  `Jarvis/jarvis.py` aparecía modificado (401 líneas) respecto a `HEAD`,
  violando aparentemente la regla de la fase 01 de no tocar ese archivo.
- **Causa raíz:** el diff era anterior a la sesión de trabajo del plan —
  cambios sin commitear del usuario, ya presentes desde antes de que se
  escribiera el plan de fases. El reviewer comparó contra `HEAD` sin
  verificar si el cambio era reciente (del builder) o preexistente (del
  usuario), y lo atribuyó por defecto al builder.
- **Cómo se detectó:** el usuario confirmó manualmente que el archivo ya
  figuraba como modificado en el `git status` inicial de la conversación,
  antes de que existiera ningún plan.
- **Solución aplicada:** se preguntó al usuario qué hacer con el archivo
  (dejarlo intacto, es trabajo suyo en progreso, no relacionado con el
  plan). Fase 01 se aprobó igual — el builder nunca tocó `jarvis.py`.
- **Estrategia para no repetirlo:** ver regla en "Reglas aprendidas"
  arriba.

## [2026-07-26] Fase 03 — self-check de recordatorios falló de forma intermitente por timing del runner

- **Qué pasó:** el self-check (`_check_recordatorios.py`) crea un
  recordatorio a "en 5 segundos", arranca `start_runner(...)` y espera
  `time.sleep(10)` antes de comprobar que el `tts_fn` de prueba recibió el
  aviso. La primera corrida falló: `avisos recibidos: []` a pesar de que el
  runner sí arrancó (`[JARVIS] Runner de recordatorios iniciado.` se
  imprimió).
- **Causa raíz:** `_loop_runner` revisa los recordatorios al entrar al
  `while True` (antes de cualquier `time.sleep`), y recién después duerme
  10s antes de la siguiente revisión. Ese primer chequeo corre a los pocos
  milisegundos de crear el hilo — antes de que pasen los 5 segundos del
  recordatorio — así que no dispara nada. El recordatorio recién vence y se
  detecta en el SEGUNDO chequeo, que ocurre ~10s después del primero (es
  decir, ~10s después de arrancar el runner, no ~5s después de crear el
  recordatorio). Esperar exactamente 10s desde la creación deja una
  ventana de carrera de milisegundos donde el assert puede correr antes de
  que el segundo chequeo del loop termine de ejecutar `_disparar`.
- **Cómo se detectó:** al correr el self-check tal cual estaba escrito
  (con `time.sleep(10)`), falló la primera vez con la lista de avisos
  vacía; al aumentar la espera a 16s pasó de forma consistente.
- **Solución aplicada:** cambiar `time.sleep(10)` a `time.sleep(16)` en el
  self-check, con un comentario explicando el porqué (margen sobre el
  segundo chequeo del loop, que ocurre a los ~10s de arrancar el runner).
- **Estrategia para no repetirlo:** ver regla en "Reglas aprendidas"
  arriba.

## [2026-07-26] Fase 03 — self-check de `tts_local.py` solo probaba el caso vacío, nunca sonó voz real

- **Qué pasó:** el reviewer aprobó la fase pero marcó como pendiente de
  confirmación humana que la voz sonara. Al pedirle al usuario escuchar,
  reportó que solo se oía el pitido del recordatorio (`winsound.Beep`),
  nunca la voz. Investigando, el self-check de `tts_local.py`
  (`_check()`) llamaba `hablar("")` — que retorna en la primera línea de
  `hablar()` sin llegar a tocar `pyttsx3` — e imprimía `OK` igual. El
  self-check nunca ejercitó el motor de voz real.
- **Causa raíz:** el smoke test se escribió para confirmar que un texto
  vacío no rompe nada (caso borde válido), pero terminó siendo el ÚNICO
  caso probado — nadie agregó una llamada con texto real. `OK` en
  consola no significaba "la voz funciona", solo "la función no explotó
  con input vacío".
- **Cómo se detectó:** el usuario reportó de oído que solo escuchaba el
  pitido, nunca la voz, al correr el flujo completo de recordatorios.
- **Solución aplicada:** se agregó una segunda llamada en `_check()`,
  `hablar("Prueba de voz de Jarvis.")`, y se corrió manualmente en vivo
  (`python -c "from app.tts_local import hablar; hablar('Hola, soy
  Jarvis. Esta es una prueba de voz.')"`) — el usuario confirmó que esta
  vez sí escuchó la voz con claridad.
- **Estrategia para no repetirlo:** ver regla en "Reglas aprendidas"
  arriba.

## [2026-07-26] Fase 04 — `youtube-search-python` fallaba siempre por incompatibilidad con `httpx` reciente

- **Qué pasó:** al instalar `youtube-search-python` (la única versión
  publicada, 1.6.6, del 2021) junto con la versión de `httpx` que trae pip
  por defecto (0.28.1), toda llamada a `VideosSearch(...).result()` tiraba
  `TypeError: post() got an unexpected keyword argument 'proxies'`. La
  librería no está mantenida y llama `httpx.post(..., proxies=self.proxy)`,
  un kwarg que `httpx` deprecó en 0.26 y eliminó en 0.28.
- **Causa raíz:** el plan solo anticipaba que la librería podía romperse
  "si YouTube cambia su API interna" (scraping frágil) — no que fallaría
  de entrada por una incompatibilidad con una dependencia transitiva sin
  pin, en un entorno limpio recién instalado.
- **Cómo se detectó:** al correr el self-check (paso 2, `buscar_youtube`)
  con una query real ("lofi hip hop radio") antes de dar la fase por
  terminada — devolvía la excepción en vez de un dict con resultado.
- **Solución aplicada:** agregar `httpx<0.28` a `requirements.txt` (con
  comentario explicando el porqué del pin) y reinstalar; con
  `httpx==0.27.2` la búsqueda funciona normalmente. No hizo falta
  implementar el fallback de scraping directo — el comentario `ponytail`
  ya documentado en `musica.py` queda como la ruta de escape si la
  librería vuelve a romperse por un cambio real de YouTube.
- **Estrategia para no repetirlo:** ver regla en "Reglas aprendidas"
  arriba.

## [2026-07-26] Fase 02 — `BASE_DIR` mal calculado en `tareas.py` guardaba datos en carpeta equivocada

- **Qué pasó:** `jarvis-reviewer` rechazó la fase porque
  `Jarvis/app/actions/tareas.py` guardaba `tareas.json` en
  `Jarvis/app/datos/tareas.json` en vez de `Jarvis/datos/tareas.json`
  (donde vive `settings.json` de la fase 01, y donde dice la propia
  docstring del módulo que debía vivir).
- **Causa raíz:** al portar el módulo se copió la fórmula
  `BASE_DIR = Path(__file__).resolve().parent.parent` de
  `Jarvis/app/config.py` sin ajustarla. `config.py` vive en
  `Jarvis/app/config.py` (dos niveles sobre `Jarvis/`, así que
  `.parent.parent` da `Jarvis/`), pero `tareas.py` vive un nivel más
  adentro, en `Jarvis/app/actions/tareas.py` (tres niveles sobre
  `Jarvis/`) — necesitaba `.parent.parent.parent`. El bug no tiraba
  ningún error: creaba silenciosamente `Jarvis/app/datos/` con el JSON
  ahí, y el self-check pasaba igual porque comparaba contra la misma
  ruta (mal) calculada por el propio módulo.
- **Cómo se detectó:** revisión manual del reviewer comparando la ruta
  esperada (consistente con `config.py`) contra la ruta real que
  resolvía `TAREAS_PATH`.
- **Solución aplicada:** cambiar a
  `BASE_DIR = Path(__file__).resolve().parent.parent.parent`, borrar la
  carpeta residual vacía `Jarvis/app/datos/`, y verificar con
  `python -c "from app.actions.tareas import TAREAS_PATH; print(TAREAS_PATH)"`
  que ahora resuelve a `Jarvis/datos/tareas.json`. Se re-corrió
  `_check_tareas.py` con resultado OK.
- **Estrategia para no repetirlo:** ver regla en "Reglas aprendidas"
  arriba.

## [2026-07-26] Fase 04 — último recurso de `open_app.py` pasa texto no filtrado a `shell=True`

- **Qué pasó:** el reviewer, auditando `_try_start_command` en
  `Jarvis/app/actions/open_app.py:335` (paso 6, último recurso cuando
  nada más matcheó), encontró que ese último intento llama
  `_try_start_command(name)` con `name` = texto normalizado del usuario
  (verbos/artículos/coletillas quitados), SIN pasar por la tabla
  `_ALIASES`. `_normalize()` limpia lenguaje natural pero no sanea
  metacaracteres de shell (`&`, `|`, `%`, `^`).
- **Causa raíz:** el plan de la Fase 04 asumía que "el target ya está
  resuelto por alias o por regex de normalización, no ejecuta texto
  arbitrario" — impreciso: ese último paso específico es la excepción.
- **Cómo se detectó:** prueba de inyección real hecha por el reviewer
  (`open_app({"app_name": "nonexistent_xyz & echo INJECTED> marker.txt"})`
  de punta a punta) — HOY no genera inyección porque el wrapping
  `f'start "" "{safe}"'` mantiene el `&` dentro de comillas parejas para
  `cmd.exe`, que no lo interpreta como separador de comandos ahí. Es
  seguro empíricamente hoy, pero es una base frágil (depende de que
  `cmd.exe` siga respetando ese quoting en todos los casos) — no una
  garantía de diseño explícita.
- **Solución aplicada:** ninguna todavía — no bloqueaba la Fase 04 (nadie
  llama `open_app` con texto de un LLM todavía, recién en Fase 05 con
  function-calling). Se dejó documentado acá y como nota explícita en
  `plans/phase-05-agente-gemini-texto.md` para endurecerlo ANTES de que
  Gemini pueda producir `app_name` libremente.
- **Estrategia para no repetirlo:** antes de exponer como tool de
  function-calling una función que en algún camino interno llega a
  `subprocess` con `shell=True`, revisar TODOS los caminos (no solo el
  camino feliz) y confirmar que ninguno reciba texto sin pasar por una
  allowlist o un filtro de metacaracteres — un camino de "último recurso"
  suele ser justo el que se pasa por alto.

## [2026-07-26] Fase 05 — instalar `google-genai` volvió a subir `httpx` y rompió `youtube-search-python`

- **Qué pasó:** al correr `pip install google-genai` (dependencia nueva de
  esta fase), pip resolvió `httpx` a 0.28.1 (versión mínima que declara
  `google-genai`), pisando el pin `httpx<0.28` que la Fase 04 había dejado
  para que `youtube-search-python` funcionara.
- **Causa raíz:** un `pip install` de un paquete nuevo resuelve el árbol de
  dependencias completo del entorno, no solo las del paquete nuevo — puede
  subir silenciosamente una dependencia transitiva compartida que otro
  paquete ya fijado necesitaba en una versión más baja, sin ningún error
  en el momento de la instalación.
- **Cómo se detectó:** al re-instalar `httpx<0.28` explícitamente después
  de instalar `google-genai`, pip mostró un warning de conflicto
  (`google-genai 2.14.0 requires httpx<1.0.0,>=0.28.1, but you have httpx
  0.27.2`); se verificó empíricamente que, a pesar del warning, ambas
  librerías funcionan igual con `httpx==0.27.2` (`client.models.list()`
  devolvió 56 modelos y `buscar_youtube("lofi hip hop radio")` siguió
  devolviendo resultado real).
- **Solución aplicada:** reinstalar `httpx<0.28` después de `google-genai`
  y volver a correr `musica._check()` (Fase 04) para confirmar que seguía
  funcionando antes de continuar. Se agregó un comentario en
  `requirements.txt` documentando que el warning de pip es un falso
  positivo en la práctica.
- **Estrategia para no repetirlo:** ver regla en "Reglas aprendidas"
  arriba.

## [2026-07-26] Fase 05 — `gemini-2.5-flash` listado por `models.list()` pero 404 al usarlo

- **Qué pasó:** el self-check (`_check_agente.py`, paso 2) falló con
  `google.genai.errors.ClientError: 404 NOT_FOUND` y el mensaje "This model
  models/gemini-2.5-flash is no longer available to new users", a pesar de
  que `client.models.list()` sí lo devolvía en la lista de 56 modelos
  disponibles (confirmado antes de escribir el código).
- **Causa raíz:** el listado de modelos de la API no refleja en tiempo
  real si un modelo sigue siendo utilizable por una cuenta/API key en
  particular — puede seguir en el catálogo (metadata) pero estar
  deprecado para cuentas nuevas.
- **Cómo se detectó:** al correr el self-check completo con
  `model="gemini-2.5-flash"` como default (tal cual sugería el plan antes
  de confirmarlo).
- **Solución aplicada:** probar modelos candidatos con una llamada real
  mínima (`generate_content(model=X, contents="di solo la palabra OK")`)
  en vez de confiar en el listado; `gemini-flash-latest` (alias que Google
  mantiene apuntando al flash recomendado vigente) sí respondió. Se
  cambió el default de `GeminiAgent` a `"gemini-flash-latest"`, con
  comentario explicando el porqué.
- **Estrategia para no repetirlo:** ver regla en "Reglas aprendidas"
  arriba.

## [2026-07-26] Fase 05 — `buscar_web` (grounding `google_search`) devuelve 429 aunque la API key es válida

- **Qué pasó:** el self-check (paso 3, precio del bitcoin) no tiró
  excepción, pero la respuesta final fue genérica ("no pude consultar la
  información en tiempo real... debido a un límite en la búsqueda web"),
  no la información concreta que pedía la Fase 05. Una prueba aislada de
  `generate_content(model="gemini-flash-latest", contents=..., config=
  GenerateContentConfig(tools=[Tool(google_search=GoogleSearch())]))`
  reprodujo el error real detrás del mensaje genérico: `429
  RESOURCE_EXHAUSTED — You exceeded your current quota`.
- **Causa raíz:** el grounding con `google_search` tiene una cuota propia,
  separada de la cuota general de `generateContent` (que sí funcionaba sin
  problema con la misma key, ver paso 2 del self-check). Cuentas sin
  billing habilitado en Google AI Studio / Cloud tienen una cuota gratis
  de grounding muy chica o nula — no es un problema del nombre de la tool
  ni del código (`types.Tool(google_search=types.GoogleSearch())` es el
  nombre correcto y vigente, confirmado contra `google.genai.types` y los
  tests del propio paquete instalado).
- **Cómo se detectó:** llamada aislada de un solo tool (`google_search`
  solo, sin `function_declarations` propias) que reprodujo el 429 directo,
  descartando que fuera un problema de mezclar tools o de nombre.
- **Solución aplicada:** ninguna en código — `buscar_web` ya maneja la
  excepción con un mensaje razonable en vez de crashear
  (`"No pude buscar en la web: {e}"`), y el agente principal reporta esa
  info al usuario en vez de fallar en seco. Queda pendiente para el
  usuario habilitar billing en su proyecto de Google AI Studio si quiere
  que el grounding funcione de verdad; no es algo que el código de esta
  fase pueda resolver.
- **Estrategia para no repetirlo:** ver regla en "Reglas aprendidas"
  arriba.

## [2026-07-26] Fase 06 — reviewer marcó RECHAZADA por checkbox sin marcar, de nuevo

- **Qué pasó:** `jarvis-reviewer` marcó la Fase 06 como RECHAZADA porque
  `plans/README.md` seguía con `- [ ] Fase 06` al momento de la revisión.
  Es el mismo patrón exacto ya visto en la Fase 01 (ver esa entrada), pero
  volvió a pasar porque la aclaración de aquella vez solo quedó en la
  entrada de la bitácora, no en las instrucciones del propio agente
  `jarvis-reviewer`.
- **Causa raíz:** las instrucciones de `.claude/agents/jarvis-reviewer.md`
  no excluían explícitamente el checkbox del "Entregable final" como algo
  fuera de su chequeo — el agente, siguiendo la lista genérica de
  "confirmar cada ítem del entregable", lo trató igual que cualquier otro
  archivo faltante.
- **Cómo se detectó:** al revisar el reporte del reviewer, coincidía
  exactamente con la Fase 01 (mismo tipo de FAIL, mismo motivo).
- **Solución aplicada:** se marcó el checkbox manualmente (correspondía
  aprobar la fase, todo lo demás estaba bien), y se editó
  `.claude/agents/jarvis-reviewer.md` agregando una excepción explícita en
  el punto 1 ("Alcance cumplido") aclarando que ese checkbox nunca es
  responsabilidad suya.
- **Estrategia para no repetirlo:** ver regla en "Reglas aprendidas"
  arriba. A diferencia de las reglas anteriores (que solo viven en esta
  bitácora), esta además se aplicó directo en las instrucciones del
  agente — corresponde hacer lo mismo con cualquier regla que un
  subagente reinterprete mal de forma repetida.

## [2026-07-26] Fase 06 — silenciar el mic salteando el envío rompía el detector de voz del servidor para el resto de la sesión

- **Qué pasó:** el usuario, probando la app real, reportó voz "lenta" y
  "muchas veces no responde". Se agregó instrumentación con timestamps
  (`print` en cada evento de `voice_engine.py`) y se detectó primero un
  problema de auto-interrupción por eco (mic+parlante del mismo equipo:
  Jarvis se escuchaba a sí mismo y el servidor lo tomaba como el usuario
  interrumpiendo). La primera corrección fue saltear el envío del chunk
  del mic (`if self.hablando: continue`) mientras sonaba la respuesta.
  Con esa corrección, el PRIMER intercambio de la sesión funcionó
  perfecto (~1 segundo de punta a punta), pero el usuario reportó que el
  SEGUNDO turno se quedó "procesando" 80 segundos sin responder nunca. El
  log mostró mic mandando chunks sin parar, pero CERO mensajes del
  servidor durante más de 30 segundos, hasta que la sesión se cortó y
  tuvo que reconectarse sola.
- **Causa raíz:** dejar de mandar audio del todo (en vez de mandar
  silencio) rompe la continuidad del stream que la Live API espera para
  su detector de actividad de voz (VAD) del lado del servidor. El primer
  ciclo de "cortar durante la respuesta, reanudar al terminar" dejó al
  detector del servidor en un estado en el que ya no volvía a reconocer
  habla nueva, sin ningún error visible — no era que "tardaba", es que el
  servidor había dejado de escuchar de verdad.
- **Cómo se detectó:** instrumentación de timestamps por evento
  (conexión, chunks de mic, primer audio de respuesta, interrupciones,
  turno completo) más un log genérico de CUALQUIER mensaje entrante del
  servidor (no solo los tipos que el código ya manejaba) — esto último
  fue clave para confirmar que el servidor no mandaba absolutamente nada,
  ni siquiera un mensaje de un tipo no contemplado.
- **Solución aplicada:** en vez de saltear `send_realtime_input` durante
  `self.hablando`, se manda un chunk de silencio (`b"\x00" * len(chunk)`)
  del mismo tamaño — mantiene el streaming continuo (sin gaps) pero sin
  el contenido real del mic que causaba el eco.
- **Estrategia para no repetirlo:** ver regla en "Reglas aprendidas"
  arriba.

## [2026-07-26] Fase 06 — `session.receive()` se agota por turno: la sesión quedaba viva pero sorda

- **Qué pasó:** persistía el síntoma "responde una vez y después se queda
  escuchando y nunca más responde", incluso después de la corrección del
  eco (entrada anterior). Además el usuario reportó "responde pero sin
  voz": la transcripción de Jarvis aparecía en pantalla pero no se
  escuchaba nada.
- **Causa raíz:** `session.receive()` del SDK `google-genai` devuelve un
  generador que se AGOTA cuando el modelo termina el turno, no uno que
  vive toda la sesión. El código tenía un `async for msg in
  session.receive():` suelto, así que la task `_recibir` terminaba
  normalmente (sin excepción) después del primer intercambio y nadie
  volvía a leer nada. La sesión seguía abierta y el mic seguía enviando,
  pero ninguna respuesta se procesaba jamás.
  Dos factores lo hicieron difícil de ver: (a) una `asyncio.Task` que
  termina no notifica nada hasta que alguien la awaitea, así que no había
  ni un log; (b) el "sin voz" era consecuencia del mismo bug — al detectar
  (ya con logging agregado) que la task había terminado, el código cerraba
  la sesión y frenaba el stream de salida en seco, descartando el audio
  que todavía estaba por reproducirse.
- **Cómo se detectó:** agregando logging explícito de `task.done()` /
  `task.exception()` en el loop principal de la sesión. Apareció
  `tarea 'recibir' terminó sin error` justo después de CADA turno
  completo — eso reveló el patrón.
- **Solución aplicada:** envolver la lectura en un `while True` que vuelve
  a pedir `session.receive()` en cada turno (`_recibir` →
  `_recibir_turno`). Además: la reproducción de audio se movió a un hilo
  aparte con su propia `queue.Queue`, porque `stream_out.write()` es
  bloqueante y estaba dentro del mismo task que leía mensajes — impedía
  procesar mensajes nuevos durante toda la respuesta de Jarvis.
- **Estrategia para no repetirlo:** ver reglas en "Reglas aprendidas"
  arriba.

## [2026-07-26] Fase 06 — configurar el VAD explícito dejó a la Live API completamente muda

- **Qué pasó:** siguiendo documentación oficial sobre calibrar el VAD
  (para atacar el síntoma "me corta lo que digo, llega incompleta"), se
  agregó `realtime_input_config` con `AutomaticActivityDetection`
  (sensibilidades + `silence_duration_ms`). Resultado: el servidor dejó de
  mandar CUALQUIER mensaje — cero transcripciones, cero audio, cero
  eventos — con el mic enviando audio normalmente todo el tiempo.
- **Causa raíz:** no determinada con precisión. Se probó primero con
  `START_SENSITIVITY_LOW` (hipótesis: demasiado insensible para detectar
  el inicio del habla) y después con `START_SENSITIVITY_HIGH`; ninguna de
  las dos hizo que llegara un solo mensaje. Es decir, no era la
  sensibilidad: la presencia misma del campo rompía la sesión con esta
  cuenta/modelo (`gemini-2.5-flash-native-audio-latest`).
- **Cómo se detectó:** comparando logs antes/después del cambio — con la
  config puesta, ni un `server_content` en 90 segundos; sacándola,
  transcripciones normales al instante.
- **Solución aplicada:** quitar `realtime_input_config` por completo y
  dejar el VAD automático por defecto, con un comentario explícito en
  `voice_engine.py` advirtiendo que no se vuelva a agregar sin probarlo.
  El síntoma original de "me corta la frase" queda pendiente de otra
  solución.
- **Estrategia para no repetirlo:** ver regla en "Reglas aprendidas"
  arriba.

## [2026-07-28] Fase 11 — re-correr `config._check()` pisó la voz real configurada por el usuario

- **Qué pasó:** al agregar `usar_auriculares` a `DEFAULTS` en `config.py`,
  se re-corrió `python -m app.config` (siguiendo la regla aprendida de
  re-validar checks existentes tras tocar un módulo compartido). El check
  pasó (`OK`), pero como efecto secundario dejó `datos/settings.json` con
  `"voice": "Kore"` — el propio `_check()` guarda `"Kore"` para probar que
  `save_settings` acepta una voz válida, y no hay forma de saber cuál era
  la voz real configurada antes (no hay control de versiones en el repo
  para diffear `settings.json`).
- **Causa raíz:** `config._check()` (de la Fase 01) no usa un archivo de
  datos aislado para pruebas — opera directo sobre
  `Jarvis/datos/settings.json`, el mismo que usa la app real. Cualquier
  re-corrida del check en un entorno con datos reales ya cargados sobreescribe
  esos datos con los valores de prueba del check.
- **Cómo se detectó:** al leer `settings.json` después de correr el check
  para confirmar que la fase no rompió nada, apareció `"voice": "Kore"` sin
  que nadie lo hubiera configurado así en esta sesión.
- **Solución aplicada:** ninguna en código (fuera del alcance de la Fase 11
  tocar el diseño de `config._check()`); se documenta acá para que el
  usuario sepa que su voz preferida puede necesitar reconfigurarse desde el
  modal si no era "Kore", y para que futuros agentes no vuelvan a pisar
  datos reales sin querer.
- **Estrategia para no repetirlo:** ver regla en "Reglas aprendidas" arriba.

## [2026-07-28] Fase 12 — `behavior=NON_BLOCKING` en la declaración compartida rompía el camino de texto con 400

- **Qué pasó:** siguiendo el plan al pie de la letra, se agregó
  `behavior=types.Behavior.NON_BLOCKING` directo en
  `_tool_declarations()` (la función compartida entre `GeminiAgent`
  de texto y `VoiceEngine`, Live). El self-check automatizable nuevo de la
  fase pasó (construir el objeto no tira error), pero al re-correr
  `_check_agente.py` (paso 2, escalar a Gemini por texto) tiró
  `google.genai.errors.ClientError: 400 INVALID_ARGUMENT.
  {'message': 'FunctionDeclaration.behavior is only supported by the
  BidiGenerateContent method'}`.
- **Causa raíz:** el plan asumía explícitamente "Ese camino no lee
  `behavior` para nada — no cambia su comportamiento síncrono existente"
  y solo pedía "confirmar esto en la verificación, no darlo por sentado".
  Al confirmarlo de verdad (correr el self-check de texto existente, no
  solo construir el objeto en Python), la asunción resultó falsa: el campo
  no es ignorado por `generate_content`, la API lo rechaza en seco. El
  SDK no valida esto en el cliente — `types.FunctionDeclaration(...,
  behavior=...)` se construye sin error, el 400 solo aparece en la llamada
  de red real.
- **Cómo se detectó:** corriendo el self-check de texto existente
  (`_check_agente.py`) después de agregar el campo, tal como pide el punto
  2 de la Verificación de la fase — no alcanzaba con el self-check nuevo
  de la fase (que solo construye el `FunctionDeclaration`, no hace una
  llamada real a `generate_content`).
- **Solución aplicada:** `_tool_declarations()` ahora toma un parámetro
  `non_blocking: bool = False`. `GeminiAgent` guarda dos variantes:
  `_tools_texto` (sin `behavior`, usada por `_resolver_con_gemini`) y
  `_tools_voz` (con `behavior=NON_BLOCKING` en `buscar_web`/`open_app`,
  expuesta por la property `tools` que ya consumía `VoiceEngine` sin
  cambios). `_check_tools_async.py` verifica ambas variantes por separado.
- **Estrategia para no repetirlo:** ver regla en "Reglas aprendidas"
  arriba.

## [2026-07-26] Fases 08/09 — índices de dispositivos del navegador usados como índices de PortAudio: Jarvis hablaba a un altavoz mudo

- **Qué pasó:** con el multi-turno ya funcionando, el usuario reportó que
  Jarvis respondía correctamente (transcripción visible, tools
  ejecutándose) pero no emitía voz.
- **Causa raíz:** el modal de Configuración llenaba los selectores de
  micrófono y altavoz con `navigator.mediaDevices.enumerateDevices()` y
  guardaba el índice de ESE listado en `settings.json`. Pero
  `VoiceEngine` (Python) usa esos índices contra PortAudio
  (`sounddevice`), cuyo orden es completamente distinto. El usuario tenía
  guardado `speaker_device_index: 3`, que en PortAudio es "Asignador de
  sonido Microsoft - Output" (dispositivo heredado que no emite sonido
  audible), mientras que la salida real del sistema era el índice 4.
  Nunca hubo error: el audio se escribía sin problema a un dispositivo que
  no suena. La imprecisión ya había sido señalada como riesgo conocido al
  construir la Fase 08, pero se dejó sin resolver por no estar pedida.
- **Cómo se detectó:** revisando `settings.json` (índices 2 y 3 guardados)
  y comparándolos contra `sounddevice.query_devices()`. Se confirmó
  reproduciendo un tono de prueba en el dispositivo por defecto: el
  usuario lo escuchó, con lo que quedó descartado un problema de audio del
  sistema.
- **Solución aplicada:** endpoint nuevo `GET /api/audio-devices` que lista
  los dispositivos reales de PortAudio desde el backend, y `app.js` ahora
  llena los selectores desde ahí (mostrando el índice real en la
  etiqueta), en vez de desde el navegador. Los valores inválidos que había
  guardados se resetearon a `-1` (predeterminado del sistema).
- **Estrategia para no repetirlo:** ver regla en "Reglas aprendidas"
  arriba.
