# Fase 18 — Prompt e identidad: instrucción de sistema única

## Objetivo

Dos motores de conversación (texto en `gemini_agent.py`, voz en
`voice_engine.py`) suenan distinto porque el de texto no tiene NINGUNA
instrucción de sistema y el de voz tiene una genérica ("breve y directa")
que no prohíbe repetir la pregunta ni define humor. Ver
`plans/INVESTIGACION-2026-07-27-voz-tools-ui.md` sección 11. Esta fase da a
los dos motores la misma identidad, con un bloque extra solo para voz.

## Contexto

Depende de **Fase 05** (`gemini_agent.py`) y **Fase 06** (`voice_engine.py`,
`_SISTEMA`). No toca tools, no toca audio, no toca `musica.py`/`navegador.py`
— el bug de YouTube reportado hoy (ver `plans/ERRORES.md`, entrada Fase 16)
queda fuera de esta fase, sin diagnosticar todavía.

## Alcance de esta fase

### 1. Prompt compartido

Nuevo módulo `Jarvis/app/persona.py` con una constante `IDENTIDAD` (texto
plano, estructura Identidad/Cómo respondés/Humor de la sección 11.4 del
documento de investigación) y una función `prompt_voz()` que devuelve
`IDENTIDAD` + el bloque `VOZ` (nada de listas/markdown/emojis, frases
cortas). Un solo lugar para editar el personaje en el futuro.

Reglas concretas que tiene que dejar explícitas (hoy no existen):
- Prohibido repetir o reformular la pregunta antes de responder — empezar
  siempre por la respuesta.
- Máximo dos frases salvo pedido explícito de detalle.
- Prohibidos los preámbulos ("Claro", "Por supuesto", "Buena pregunta").
- Humor ácido/ironía seca, como mucho un comentario por respuesta, después
  de la información útil nunca en lugar de ella, nunca sobre la persona.
- Avisos (recordatorios) van seco y claro primero, sin chiste encima.

Sin nombre de usuario hardcodeado (no hay dato confiable de con quién habla
todavía) — identidad genérica "quien te habla", no "[nombre]" del borrador
original.

### 2. Aplicar a texto

`gemini_agent.py::_resolver_con_gemini` — agregar
`system_instruction=persona.IDENTIDAD` al `GenerateContentConfig` que ya
arma (línea ~191). Mismo cambio en `_buscar_web` si aplica sin romper el
grounding (la request de `google_search` es una request separada, ver
comentario existente en el código).

### 3. Aplicar a voz

`voice_engine.py` — reemplazar `_SISTEMA` por `persona.prompt_voz()`.

## Fuera de alcance

- Formato de personaje / selector (`Fase 19` en adelante, ver README).
- Inyectar contexto dinámico (hora, tareas pendientes) en el prompt — es la
  idea de la sección 11.4 del documento para hacer el humor específico, pero
  es una fase aparte (necesita leer `tareas.json`/`recordatorios.json` en
  cada arranque de sesión).
- `safety_settings` — si el humor ácido empieza a ser rechazado por filtros
  de seguridad en uso real, se ajusta en una fase de seguimiento con
  evidencia real, no preventivamente.
- El bug de YouTube (Fase 16) — ya registrado en `plans/ERRORES.md`, no se
  toca acá.

## Verificación

1. Texto: preguntarle algo simple por el chat escrito, confirmar que NO
   reformula la pregunta y que el tono coincide con voz.
2. Voz: hacer una pregunta simple, confirmar que arranca directo por la
   respuesta, sin "Por supuesto, tu pregunta es...".
3. Probar un caso de humor (ej. preguntar la hora con una tarea vencida
   hace días, aunque el prompt no inyecte esos datos todavía — el humor
   genérico igual debe sonar seco, no forzado).
4. Probar un recordatorio/aviso real, confirmar que NO lleva chiste.
5. Manual, con logs de consola frescos como en fases anteriores.

## Entregable final de la fase

- `Jarvis/app/persona.py` nuevo, con `IDENTIDAD` y `prompt_voz()`.
- `gemini_agent.py` con `system_instruction` en la request de texto.
- `voice_engine.py` usando `persona.prompt_voz()` en vez de `_SISTEMA` local.
- Marcar `- [x] Fase 18` en `plans/README.md` (agregar la fila a la tabla,
  hoy falta — ver nota en la línea "Fases 18+... aún no tienen archivo
  propio").
