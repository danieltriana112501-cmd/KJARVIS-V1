# Fase 03 — Recordatorios y alarmas + runner en background

## Objetivo

Portar el sistema de recordatorios/alarmas del proyecto de referencia HRZ
(el módulo más sólido de todo ese proyecto), con su runner en segundo plano
que revisa la hora real del sistema y dispara avisos, y conectar el aviso a
un TTS **local** (no a Gemini — el objetivo es que anunciar un recordatorio
no gaste cuota de API).

## Contexto

Depende de **Fase 01** (estructura de carpetas) y puede desarrollarse en
paralelo a la Fase 02 (no depende de tareas). Sí es un requisito para la
Fase 07 (morning brief) y Fase 05 (el agente de Gemini expone esto como
tool).

Fuente de referencia (ya revisada en el diseño):
`JARVIS-HRZ proyecto para clonar o copiar inspirarse y mejorar/_internal/actions/recordatorios.py`
(854 líneas). Es el módulo a portar casi completo. Contiene:

- Parseo de fecha/hora en lenguaje natural español (`resolver_datetime`):
  "en 5 minutos", "mañana a las 10", "el lunes a las 9", "en 2 horas y 30
  minutos", etc.
- Separación en dos archivos: `recordatorios.json` (avisos simples) y
  `alarmas.json` (avisos con una instrucción de acción asociada,
  `action_prompt`).
- Recurrencia: `none | daily | weekly | weekdays` (con lista de días
  0=lunes..6=domingo).
- Runner en background (`_loop_runner`, revisa cada 10s) que dispara los
  que vencieron, reprograma los recurrentes, y desactiva (no borra) los que
  no se repiten.
- Tono sonoro vía `winsound.Beep` (ya es local, sin dependencias externas,
  Windows-only — el proyecto ya es Windows-only según el `.gitignore` y
  requirements, así que esto es aceptable tal cual).

## Alcance de esta fase

### 1. Copiar y adaptar `recordatorios.py`

Crear `Jarvis/app/actions/recordatorios.py` a partir del archivo de
referencia, con estos cambios:

- Mismo ajuste de rutas relativas que en la Fase 02
  (`BASE_DIR / "datos"`, ya coincide con la estructura existente).
- **Cambio importante respecto al original:** en el HRZ, `_disparar()` usa
  `inject_fn(...)` para mandarle un mensaje largo a la sesión de Gemini y
  que el LLM "anuncie con estilo" el recordatorio (ver líneas 733–767 del
  original). **Esto se reemplaza**: la función `_disparar()` en la versión
  nueva NO debe llamar a ningún LLM. En cambio, debe llamar directo a una
  función de síntesis de voz local (inyectada como parámetro, ej.
  `tts_fn(texto: str)`), leyendo tal cual el campo `message` (o
  `action_prompt` si es una alarma con instrucción — en ese caso, para
  esta fase, simplemente se lee el texto de `action_prompt` en voz alta,
  SIN ejecutar ninguna acción real; ejecutar la instrucción de una alarma
  con herramientas reales queda fuera de alcance de esta fase, ver sección
  "Fuera de alcance").
- Mantener intacto: el parseo de fechas, la recurrencia, el guardado
  separado por tipo, el runner en background, y el beep de aviso.

### 2. Matcher local para recordatorios

Extender `Jarvis/app/matcher.py` (creado en la Fase 02) con reglas para
recordatorios:

| Frase de ejemplo | Acción resuelta |
|---|---|
| "recuérdame [algo] en/a las/mañana ..." | `recordatorios` action=`add`, kind=`reminder` |
| "pon una alarma para ..." / "despiértame a las ..." | `recordatorios` action=`add`, kind=`alarm` |
| "qué recordatorios tengo" / "mis alarmas" | `recordatorios` action=`list` |
| "cancela el recordatorio de ..." / "borra la alarma de ..." | `recordatorios` action=`delete` |

Ojo: distinguir "recuérdame que tengo que llamar al doctor mañana" (esto es
un candidato válido tanto para `tareas.add` como para `recordatorios.add`
con `kind=reminder`) — la regla de desambiguación para este matcher local:
si el texto tiene una hora explícita (ej. "a las 5", "en 20 minutos") →
`recordatorios`; si solo tiene fecha sin hora y suena a pendiente por
hacer (contiene "tarea", "pendiente", o no tiene ninguna palabra de
tiempo relativo corto como "en N minutos/horas") → `tareas`. Si hay duda
real, devolver `None` y dejar que lo resuelva Gemini en la Fase 05 (mejor
no resolver mal que resolver rápido y mal).

### 3. Arranque del runner

Exponer en `Jarvis/app/actions/recordatorios.py` la función
`start_runner(tts_fn, player=None)` (versión simplificada de la firma
original `start_runner(inject_fn, speaking_fn, player, jarvis)` — acá no
hay objeto `jarvis` todavía porque no existe el loop principal hasta la
Fase 05, así que la firma se reduce a lo que de verdad se usa en esta
fase). Debe ser idempotente (ya lo es en el original, mantener el patrón
`_runner_started` global).

## Fuera de alcance

- Ejecutar la instrucción de una alarma con herramientas reales (ej. "que
  Jarvis abra Spotify y ponga música cuando suene la alarma") — eso
  requiere el agente de Gemini con function-calling completo, se conecta
  recién en la Fase 05 (ahí se debe volver a esta función y cablear
  `action_prompt` al agente en vez de solo leerlo en voz). Dejar un
  comentario `# TODO fase-05:` en el punto exacto del código donde se lee
  `action_prompt` sin ejecutarlo, para que la Fase 05 lo encuentre fácil.
- Interfaz gráfica de recordatorios (Fase 08).
- TTS real: para esta fase, `tts_fn` puede ser una función mínima con
  `pyttsx3` (ya está en `requirements.txt` del proyecto original) — no
  hace falta esperar a la Fase 06 (voz Gemini Live) para tener algo audible
  y probable. Crear `Jarvis/app/tts_local.py` con una función
  `hablar(texto: str)` usando `pyttsx3`, reutilizable por otras fases.

## Verificación

Script de self-check que:

1. Crea un recordatorio con `crear_recordatorio("probar sistema", when="en 5 segundos")`.
2. Arranca el runner con un `tts_fn` que solo hace `print(f"[TTS] {texto}")`.
3. Espera ~10 segundos (`time.sleep`) y confirma en la salida que se
   imprimió el aviso.
4. Confirma que `match_local("qué recordatorios tengo")` devuelve la acción
   `list` esperada.
5. Imprime `OK` o el detalle del fallo.

## Entregable final de la fase

- `Jarvis/app/actions/recordatorios.py` funcionando standalone, con TTS
  local en vez de LLM.
- `Jarvis/app/tts_local.py` con `hablar()`.
- Reglas de recordatorios agregadas a `Jarvis/app/matcher.py`.
- Self-check pasando (incluye esperar a que dispare un recordatorio real).
- Marcar `- [x] Fase 03` en `plans/README.md`.
