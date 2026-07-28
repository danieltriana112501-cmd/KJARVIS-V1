# Planes de implementación — Jarvis (versión personal)

Este directorio contiene el plan de construcción del asistente, dividido en
**fases cortas e independientes**. Cada archivo `phase-NN-*.md` está escrito
para que un agente de IA (sin memoria de conversaciones previas) lo lea y
ejecute directamente, tocando código.

## Cómo usar estos planes

- Ejecutar las fases **en orden** (cada una declara sus dependencias).
- Cada fase es un commit/sesión de trabajo razonable — no hace falta
  encadenar varias fases en una sola sesión.
- El humano a cargo del proyecto decide, fase por fase, si continuar según
  su cuota diaria disponible del agente de IA que use para ejecutarlas.
- Ninguna fase debe adelantar trabajo de fases futuras ni improvisar
  funcionalidades fuera de su alcance declarado.

## Contexto del proyecto (leer antes de cualquier fase)

Este es un fork/evolución de un proyecto open source simple
(`Jarvis-Desktop-Voice-Assistant`, MIT license) hacia un asistente de voz
personal más completo, **para uso propio y de gente cercana, NO comercial**.
No lleva sistema de suscripción, ni autenticación Firebase, ni ofuscación —
eso se descartó deliberadamente.

Hubo un proyecto comercial de referencia (`JARVIS-HRZ`, carpeta separada en
este repo, solo para inspiración — su análisis de seguridad está en
`JARVIS-HRZ proyecto para clonar o copiar inspirarse y mejorar/analisis_completo_jarvis.md`)
del que se reutilizan **algunos módulos de código fuente ya extraídos**
(no compilados) ubicados en:
`JARVIS-HRZ proyecto para clonar o copiar inspirarse y mejorar/_internal/actions/`

Módulos de ahí que SÍ se adaptan (referenciados en las fases correspondientes):
`tareas.py`, `recordatorios.py`, `open_app.py`, `spotify_control.py`,
`weather_report.py` / `clima_panel.py`, `morning_brief.py`.

Módulos de ahí que NO se copian nunca (riesgo de seguridad, fuera de alcance):
`self_edit.py`, `auto_programmer.py`, `terminal_agent.py`, `screen_vision.py`,
`vision_guardian.py`, `smart_file_organizer.py`, todo el sistema Firebase/planes.

## Principios que TODAS las fases deben respetar

1. **Ahorro de cuota de API de Gemini**: cualquier acción determinista
   (agregar/listar/completar tarea, crear/listar recordatorio, decir la hora,
   abrir una app conocida) se resuelve con un **matcher local** (regex/keywords)
   ANTES de considerar llamar a Gemini. Gemini solo se usa cuando la frase no
   matchea ningún patrón conocido, o cuando la tarea requiere razonamiento o
   búsqueda real.
2. **Nunca ejecutar comandos de shell arbitrarios generados por el LLM.**
   Ninguna herramienta debe usar `subprocess.run(..., shell=True)` con un
   string libre proveniente del modelo o del usuario sin allowlist.
3. **Nada de red expuesta fuera de localhost.** Cualquier servidor Flask local
   debe bindear a `127.0.0.1`, nunca a `0.0.0.0`.
4. **Estética de interfaz:** negro/blanco, estilo cómic Watch Dogs 2 (línea
   blanca gruesa sobre fondo negro, textura halftone sutil, tipografía
   monoespaciada, sin colores de acento — el detalle completo de la guía de
   estilo está en `phase-08-interfaz-base.md`, sección "Guía visual").
5. **Nada de comentarios explicando qué hace el código** (el nombre de las
   funciones ya lo dice); solo comentarios que expliquen un porqué no obvio.

## Índice de fases

| Fase | Archivo | Qué construye | Depende de |
|---|---|---|---|
| 01 | `phase-01-scaffold-config.md` | Estructura de carpetas + módulo de configuración (API key, voz, mic/altavoz) | — |
| 02 | `phase-02-tareas.md` | Gestor de tareas (pendiente/hecho) + matcher local | 01 |
| 03 | `phase-03-recordatorios.md` | Recordatorios y alarmas + runner en background + aviso por TTS local | 01 |
| 04 | `phase-04-apps-musica.md` | Abrir apps + reproducir música (YouTube web, sin Spotify API) | 01 |
| 05 | `phase-05-agente-gemini-texto.md` | Agente Gemini de texto con function-calling + búsqueda con grounding | 01, 02, 03, 04 |
| 06 | `phase-06-voz-gemini-live.md` | Motor de voz nativo (Gemini Live API), sesión bajo demanda | 05 |
| 07 | `phase-07-clima-morning-brief.md` | Clima (Open-Meteo) + resumen matutino programado | 02, 03, 05 |
| 08 | `phase-08-interfaz-base.md` | Interfaz pywebview + Flask, estilo Watch Dogs 2, sidebar + modales | 01–05 |
| 09 | `phase-09-ascii-panel.md` | Panel central con animación ASCII reactiva al estado de voz | 06, 08 |
| 10 | `phase-10-pip-overlay.md` | Ventana flotante mini (picture-in-picture) siempre encima | 09 |

## Estado

Marcar aquí manualmente a medida que se completan (cada fase también debe
actualizarse a sí misma si aplica):

- [x] Fase 01
- [x] Fase 02
- [x] Fase 03
- [x] Fase 04
- [x] Fase 05
- [x] Fase 06
- [ ] Fase 07
- [x] Fase 08
- [x] Fase 09
- [ ] Fase 10
