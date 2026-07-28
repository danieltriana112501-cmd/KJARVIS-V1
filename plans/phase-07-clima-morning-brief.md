# Fase 07 — Clima + resumen matutino (morning brief)

## Objetivo

Agregar consulta de clima (sin API key, servicio gratuito) y un resumen
matutino programado que combine clima + tareas del día + recordatorios
pendientes, anunciado por voz automáticamente a una hora configurable.

## Contexto

Depende de las **Fases 02, 03, 05** (usa tareas, recordatorios, y el
agente para redactar el resumen final en lenguaje natural). Estas dos
funcionalidades (`weather_report.py`/`clima_panel.py` y
`morning_brief.py`) fueron señaladas explícitamente por el usuario como las
que quiere sumar del proyecto de referencia HRZ, con la salvedad de que
`smart_file_organizer.py` **no** se suma (descartado por exceso de
permisos/riesgo — no reabrir esa decisión).

## Alcance de esta fase

### 1. Módulo de clima

Crear `Jarvis/app/actions/clima.py`. Usar **Open-Meteo**
(`https://open-meteo.com`) — servicio gratuito que no requiere API key ni
registro, tiene endpoint de geocoding (`geocoding-api.open-meteo.com`) para
convertir nombre de ciudad a lat/lon, y endpoint de pronóstico
(`api.open-meteo.com`). No portar ningún código del HRZ para esto (esos
módulos no fueron revisados en detalle durante el diseño y probablemente
dependían de otra API con key) — implementar directo contra Open-Meteo.

```python
def clima(parameters: dict, player=None) -> str:
    """
    Acciones: hoy | manana (o cualquier acción simple, mantener mínimo).
    Lee la ubicación desde config.get("location") (ciudad guardada en la
    Fase 01). Si location está vacía, devuelve un mensaje pidiendo que se
    configure la ubicación primero (no falla ni asume una ciudad default).
    """
```

Cachear el resultado del geocoding (ciudad → lat/lon) en
`Jarvis/datos/clima_cache.json` para no repetir esa consulta en cada
llamada — el pronóstico en sí SÍ se pide fresco cada vez (no cachear el
clima, solo la geolocalización de la ciudad, que no cambia).

### 2. Matcher local

Agregar a `Jarvis/app/matcher.py`:

| Frase de ejemplo | Acción resuelta |
|---|---|
| "cómo está el clima" / "qué clima hace" / "va a llover" | `clima` action=`hoy` |
| "cómo va a estar el clima mañana" | `clima` action=`manana` |

### 3. Morning brief

Crear `Jarvis/app/actions/morning_brief.py`:

```python
def generar_brief(agente: GeminiAgent) -> str:
    """
    Junta: clima de hoy + lista de tareas pendientes con fecha de hoy +
    recordatorios/alarmas de hoy. Le pasa ese contexto crudo a
    `agente.procesar(...)` con una instrucción de sistema para que lo
    redacte como un saludo natural breve (no una lista telegráfica), y
    devuelve el texto final.
    """
```

Esta función SÍ usa Gemini (no tiene sentido resolverla con matcher local
porque necesita redactar un resumen natural combinando 3 fuentes) — pero
es una sola llamada a la vez que se dispara, no algo que se repita
seguido, así que el gasto de cuota es aceptable.

### 4. Programación horaria

Reutilizar el mismo mecanismo de "runner en background" que ya existe en
`recordatorios.py` (Fase 03) en vez de crear un sistema de scheduling
nuevo — la forma más simple: al iniciar la aplicación, si el usuario
configuró una hora de brief matutino (nuevo campo en
`Jarvis/app/config.py`: agregar `"morning_brief_time": ""` a `DEFAULTS`,
ej. `"08:00"`, vacío = desactivado), crear internamente un recordatorio
recurrente diario (`kind="alarm"`, `recurrence="daily"`) cuyo
`action_prompt` sea un marcador interno reconocible (ej.
`"__morning_brief__"`) que, al dispararse en `_disparar()`
(`recordatorios.py`), en vez de mandarse a `agente.procesar()` como
cualquier otro `action_prompt`, se detecte ese marcador especial y se
llame a `generar_brief(agente)` en su lugar. Esto evita construir un
segundo sistema de scheduling desde cero — reutiliza el que ya existe y
ya está probado.

Documentar este acoplamiento con un comentario en `recordatorios.py` en el
punto donde se agrega la detección del marcador, indicando por qué existe
(evitar duplicar el runner).

### 5. Configuración de ubicación y hora de brief

Extender el módulo de configuración (Fase 01) — ya tiene el campo
`location`; agregar `morning_brief_time`. Sin interfaz gráfica todavía
(Fase 08 le da UI), pero debe poder configurarse editando
`Jarvis/datos/settings.json` a mano o vía `config.set(...)` desde un
script, para poder probar esta fase de forma aislada.

## Fuera de alcance

- No hay UI para configurar ubicación/hora todavía (Fase 08).
- No se agrega ningún otro dato al brief (noticias, agenda de calendario,
  etc.) — el usuario pidió específicamente clima + tareas + recordatorios,
  no más que eso por ahora.

## Verificación

Self-check (`Jarvis/app/actions/_check_clima_brief.py`):

1. `config.set("location", "Lima, Perú")` (o la ciudad real del usuario).
2. `clima({"action": "hoy"})` → confirma que devuelve texto con temperatura
   y condición (no vacío, no error).
3. Crea una tarea de prueba con fecha de hoy y un recordatorio de prueba
   para hoy.
4. Llama `generar_brief(agente)` y confirma que el texto devuelto menciona
   el clima Y la tarea de prueba (verificación por substring, no exacta).
5. Imprime `OK` o detalle del fallo.

## Entregable final de la fase

- `Jarvis/app/actions/clima.py` funcionando con Open-Meteo (sin API key).
- `Jarvis/app/actions/morning_brief.py` funcionando.
- `config.py` extendido con `location` (ya existía) y
  `morning_brief_time`.
- Marcador interno de brief conectado al runner de recordatorios.
- Marcar `- [x] Fase 07` en `plans/README.md`.
