# Fase 12 — Tools que no bloquean el turno: async + relleno + caché

## Objetivo

Que Jarvis no se quede mudo mientras `buscar_web` hace una request completa
de grounding o `open_app` escanea el Menú Inicio. La Live API soporta tools
`NON_BLOCKING` con `scheduling` (`INTERRUPT`/`WHEN_IDLE`/`SILENT`) — hoy no
se usa, todo tool_call es síncrono y bloquea el turno hasta que termina.

Referencia: `plans/INVESTIGACION-2026-07-27-voz-tools-ui.md`, hallazgo #4
del resumen ejecutivo, secciones 2.3 y 4.3.

## Contexto

Depende de la **Fase 06** (`voice_engine.py`, sesión Live) y **Fase 05**
(`gemini_agent.py`, declaraciones de tools compartidas entre texto y voz).

**Restricción de la API, confirmada contra la versión instalada
(`google-genai 2.14.0`)**: `types.FunctionDeclaration` acepta `behavior:
Behavior` (`BLOCKING`/`NON_BLOCKING`, default `BLOCKING`) y
`types.FunctionResponse` acepta `scheduling: FunctionResponseScheduling`
(`SILENT`/`WHEN_IDLE`/`INTERRUPT`) — verificado con
`python -c "from google.genai import types; print(list(types.Behavior))"` y
el equivalente para `FunctionResponseScheduling`. La doc oficial dice que
async function calling **no** está soportado en `gemini-3.1-flash-live`,
solo en `gemini-2.5-flash-live` — el modelo que usa este proyecto
(`voice_engine.py:47`).

Código actual relevante:

- `Jarvis/app/gemini_agent.py:97-127` — `_tool_declarations()`, compartida
  por el agente de texto (`generate_content`, síncrono) y por
  `VoiceEngine` (Live, vía `self.agente.tools`, `gemini_agent.py:145-149`).
- `Jarvis/app/voice_engine.py:367-380` — manejo de `msg.tool_call`: hoy
  itera las function calls, las ejecuta con
  `await loop.run_in_executor(...)` **una por una y en secuencia**, y
  recién cuando todas terminaron manda `session.send_tool_response` con
  todas las respuestas juntas. Mientras tanto el modelo no tiene nada que
  decir — silencio.
- `Jarvis/app/actions/open_app.py:244-270` — `_scan_start_menu`: hace
  `root.rglob("*.lnk")` sobre las dos carpetas de Menú Inicio **en cada
  llamada**, sin ningún tipo de caché.
- `Jarvis/app/voice_engine.py:36-39` — `_SISTEMA`, instrucción de sistema
  de voz.

**Importante — no confundir dos capas distintas:**
1. El campo `behavior` en la declaración de la tool es lo que le dice al
   modelo "esta función puede tardar, no me bloquees el turno esperándola".
2. El código de `voice_engine.py` que maneja `msg.tool_call` es el que
   decide, en la práctica, si espera el resultado antes de seguir leyendo
   mensajes o si lo dispara en paralelo y responde después. Marcar
   `NON_BLOCKING` sin cambiar ese código no alcanza — hay que hacer las dos
   cosas.

## Alcance de esta fase

### 1. Marcar `buscar_web` y `open_app` como `NON_BLOCKING`

En `gemini_agent.py:_tool_declarations()`, agregar
`behavior=types.Behavior.NON_BLOCKING` a las `FunctionDeclaration` de
`buscar_web` y `open_app` únicamente. El resto (`tareas`, `recordatorios`,
`musica`) queda `BLOCKING` (default, sin cambios) — son deterministas y
rápidas, no lo necesitan.

Esta declaración es compartida con el agente de texto
(`_resolver_con_gemini`, que usa `generate_content` normal, no Live). Ese
camino no lee `behavior` para nada — no cambia su comportamiento síncrono
existente. Confirmar esto en la verificación (punto 3 más abajo), no
darlo por sentado.

### 2. `voice_engine.py`: no esperar en línea a las tools `NON_BLOCKING`

En el manejo de `msg.tool_call` (`_recibir_turno`, `voice_engine.py:367`),
separar el comportamiento según el nombre de la function call:

- **Tools `BLOCKING`** (`tareas`, `recordatorios`, `musica`): mismo
  comportamiento que hoy — `await` en línea, responder antes de seguir.
- **Tools `NON_BLOCKING`** (`buscar_web`, `open_app`): en vez de
  `await`, lanzar la ejecución con `asyncio.create_task(...)` y **no
  bloquear** el resto de `_recibir_turno` — la tarea, al terminar, arma su
  propio `types.FunctionResponse` (con `id`/`name` de la llamada original)
  y llama `await session.send_tool_response(...)` por su cuenta, de forma
  independiente del resto del loop. Guardar una referencia a la tarea
  (ej. en una lista de instancia) para que no la recolecte el garbage
  collector a mitad de camino — es un error clásico de `asyncio` con tasks
  "fire and forget".
- Asignar el `scheduling` según la tool: `buscar_web` → `WHEN_IDLE` (que
  termine de decir lo que estaba diciendo antes de reportar el resultado);
  `open_app` → `INTERRUPT` (el usuario quiere confirmación de que se abrió
  ya, cortando lo que esté diciendo si hace falta).

### 3. Frases de relleno

Agregar una línea a `_SISTEMA` (`voice_engine.py:36-39`) instruyendo que,
cuando vaya a usar `buscar_web` o `open_app`, diga algo corto antes de
tener el resultado (ej. "dale, un segundo" / "ya me fijo") en vez de
quedarse en silencio total. No es un mecanismo garantizado —- es una
instrucción de prompt, barata, complementaria al cambio de scheduling. No
tocar el resto del prompt de voz acá — reescribirlo entero es la Fase 17.

### 4. Caché en memoria del Menú Inicio

En `open_app.py`, cachear el escaneo de `.lnk` a nivel de módulo (caché de
proceso, se pierde al reiniciar la app — alcanza, ver sección 4.3 de la
investigación): una función que escanea las dos carpetas de Menú Inicio
**una sola vez**, guarda la lista de `(stem_lowercase, ruta)`, y
`_scan_start_menu` hace el fuzzy-match sobre esa lista en memoria en vez de
volver a recorrer el filesystem en cada llamada.

## Fuera de alcance

- **`musica` / `buscar_youtube`** — sigue síncrona. El scraping es lento
  pero es una fase aparte (Fase 15 ya la tiene: sacar
  `youtube-search-python`); no mezclar los dos cambios.
- **`tareas` / `recordatorios`** async — son deterministas y rápidas, no
  hace falta.
- **Combinar `google_search` nativo con `function_declarations` en la
  misma sesión Live** (sección 4.4 de la investigación) — es un cambio de
  arquitectura distinto (reemplazaría `buscar_web` en voz), no una
  optimización de la tool actual. Queda anotado para evaluar aparte, no
  para esta fase.
- **Invalidación del caché del Menú Inicio** (por fecha de modificación de
  las carpetas, o comando manual de refresco) — la versión de esta fase es
  caché de proceso sin invalidación; si se instala una app nueva hace
  falta reiniciar Jarvis para que aparezca. Aceptable para esta fase,
  documentarlo como limitación conocida, no resolverlo acá.
- **Tocar `realtime_input_config` / VAD** — Fase 13, separada a propósito.
- **Reescribir el prompt completo de voz** — Fase 17. Esta fase solo agrega
  la línea puntual de frases de relleno.

## Verificación

Automatizable:

1. `python -c "from google.genai import types; types.FunctionDeclaration(name='x', behavior=types.Behavior.NON_BLOCKING)"` no debe tirar error (confirma que la versión instalada soporta el campo, ya verificado en esta sesión pero repetirlo como parte del self-check de la fase).
2. Correr el self-check de texto existente (`_check_agente.py` o equivalente) y confirmar que `buscar_web`/`open_app` siguen funcionando igual por el camino de texto (`generate_content`), sin que el campo `behavior` nuevo rompa nada ahí.
3. Caché de Menú Inicio: llamar `open_app` dos veces seguidas con nombres distintos y loguear el tiempo de cada `_scan_start_menu` — la segunda debe ser notablemente más rápida que la primera (no repite el `rglob`).

Manual, con la app real (requiere sesión de voz activa):

4. Pedirle a Jarvis por voz que busque algo en internet. Confirmar que dice una frase corta ("un segundo...") y sigue escuchando/respondiendo con normalidad mientras la búsqueda corre — no debe quedarse mudo ni trabado.
5. Pedirle que abra una aplicación. Confirmar que confirma rápido que la abrió (scheduling `INTERRUPT`), sin esperar a que termine de decir otra cosa.
6. Confirmar que `tareas`/`recordatorios`/`musica` siguen respondiendo igual que antes (sin regresión de latencia ni de comportamiento por el cambio en el manejo de `tool_call`).

## Entregable final de la fase

- `buscar_web` y `open_app` declarados `NON_BLOCKING` en `gemini_agent.py`.
- `voice_engine.py` maneja `tool_call` distinguiendo `BLOCKING` de
  `NON_BLOCKING`: las segundas no bloquean el loop de recepción, y
  responden con el `scheduling` que corresponda cuando terminan.
- Línea de frases de relleno agregada a `_SISTEMA`.
- Caché en memoria del escaneo del Menú Inicio en `open_app.py`.
- Marcar `- [x] Fase 12` en `plans/README.md`.
