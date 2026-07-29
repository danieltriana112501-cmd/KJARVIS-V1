# Fase 14 — VAD: agregar `prefix_padding_ms` en aislado, nada más

## Objetivo

El usuario confirmó auriculares reales puestos (descarta eco físico como
causa) y reporta: "me toca gritar" para que el mic responda bien (ya
arreglado en Fase 13, era la escala de la barra) y, más grave, **la IA
detecta interrupciones que no pasaron** — respuestas cortadas, y a veces
vuelve a responder como si la hubieran interrumpido sin que el usuario haya
dicho nada. Con auriculares puestos, esto no puede ser el gate de RMS de la
Fase 11 (bypaseado por diseño cuando `usar_auriculares=true`) — es el VAD
automático **del servidor** de la Live API interpretando mal algo como
habla del usuario.

Referencia: `plans/INVESTIGACION-2026-07-27-voz-tools-ui.md`, hallazgo #7
del resumen ejecutivo, sección 2.4.

## Contexto — LEER ANTES DE TOCAR NADA

`plans/ERRORES.md`, entrada de Fase 06: agregar `realtime_input_config`
dejó al servidor **completamente mudo** (cero mensajes, ni una
transcripción), con `START_SENSITIVITY_LOW` y con `HIGH`. Causa no
determinada en su momento. `voice_engine.py:200-206` tiene un comentario
explícito **"NO agregar `realtime_input_config` acá"** dejado por esa
experiencia.

La investigación encontró una pista que esa entrada no consideró: la
documentación oficial de la Live API dice que el ejemplo que ella misma
muestra usa `silence_duration_ms: 100`, un valor que la misma página
después desaconseja (recomienda 500-800ms; por debajo de 500ms se
fragmenta el habla). Es una hipótesis razonable de que la Fase 06 copió
ese ejemplo y el valor bajo fue la causa real, no el campo en sí — pero es
una hipótesis, no un hecho confirmado. **Por eso esta fase toca UNA sola
cosa, aislada, y se detiene ante el primer indicio de problema.**

**Regla no negociable de esta fase (ya establecida en `plans/README.md`,
sección "Reglas de trabajo"): una variable por vez.** Esta fase agrega
ÚNICAMENTE `prefix_padding_ms`. No agrega `silence_duration_ms`, no toca
sensibilidades (`start_of_speech_sensitivity` / `end_of_speech_sensitivity`),
no pone `disabled: true`. Si esta fase sobrevive y el usuario la confirma
funcionando, esas son fases futuras separadas (15, 16...), no pasos
agregados acá después.

`prefix_padding_ms` es, de los campos disponibles, el que tiene menos
chance de causar el mismo desastre que `silence_duration_ms`/sensibilidad:
solo agrega audio ANTES del punto donde el servidor detectó inicio de
habla (default 20ms, muy poco margen) — no cambia CUÁNDO el servidor
decide que alguien empezó o dejó de hablar, que es lo que rompió la Fase
06. Aun así, se trata como riesgo real hasta confirmar lo contrario.

## Alcance de esta fase

### 1. Agregar `realtime_input_config` con SOLO `prefix_padding_ms`

En `Jarvis/app/voice_engine.py`, dentro de `_sesion_async`, en
`live_config` (`LiveConnectConfig`), agregar:

```python
realtime_input_config=types.RealtimeInputConfig(
    automatic_activity_detection=types.AutomaticActivityDetection(
        prefix_padding_ms=300,
    ),
),
```

Reemplazar el comentario actual que dice "NO agregar `realtime_input_config`
acá" por uno que documente QUÉ se agregó, POR QUÉ (referencia a esta fase y
a la hipótesis del `silence_duration_ms` bajo en la doc oficial), y que dej
una advertencia hacia adelante: si el servidor se queda mudo de nuevo con
SOLO este campo aislado, la próxima persona que toque esto debe saber que
no fue una combinación de campos — fue este campo específico, y hay que
documentarlo como limitación real del modelo con esta cuenta, no reintentar
a ciegas.

### 2. Logging para poder confirmar (instrumentar antes de dar por bueno)

Ya existe bastante logging con timestamp en `voice_engine.py`
(`[VoiceEngine][hh:mm:ss] ...`). Confirmar que alcanza para ver, en una
sesión de prueba: cuándo conecta, cuándo llega la primera transcripción de
usuario, cuándo llega audio de respuesta, y cuándo se marca
`interrumpido por el usuario` (línea existente en `_recibir_turno`). Si
falta alguno de esos puntos para poder diagnosticar "se interrumpió solo",
agregarlo — pero no más allá de eso, no instrumentar todo el archivo de
nuevo.

## Fuera de alcance

- **`silence_duration_ms`** — la hipótesis más fuerte para el síntoma
  reportado (interrupciones que fragmentan por pausas naturales), pero
  **queda para una fase futura, después de confirmar que
  `prefix_padding_ms` solo no rompe nada**. No agregarlo en esta fase aunque
  parezca el fix más directo — es exactamente la tentación que causó el
  desastre de Fase 06.
- **`start_of_speech_sensitivity` / `end_of_speech_sensitivity`** — al
  final de la lista según la investigación, no tocar todavía.
- **`disabled: true` + VAD manual (`activity_start`/`activity_end` con
  `webrtcvad`/`silero-vad`)** — alternativa de fondo mencionada en la
  investigación si el VAD del servidor resulta no ser confiable ni
  ajustado; es un cambio de arquitectura mucho más grande, no esta fase.
- **Tocar el gate de RMS de la Fase 11 o el flag de auriculares** — ya
  confirmado que no es la causa con auriculares reales puestos.

## Verificación

Automatizable (sin voz real):

1. `python -c "from google.genai import types; types.RealtimeInputConfig(automatic_activity_detection=types.AutomaticActivityDetection(prefix_padding_ms=300))"` no debe tirar error — confirma que el SDK instalado soporta la construcción del objeto (repetir la lección de Fase 12: que el SDK lo acepte al construirlo no garantiza que el servidor lo acepte en la llamada real — este punto NO reemplaza la prueba manual de abajo).
2. Importar `app.voice_engine` sin error, y correr el self-check existente (`python -m app.voice_engine`) — confirma que no se rompió nada de la Fase 11 de paso.

**Manual, OBLIGATORIA y no reemplazable por ningún self-check — este es el
punto central de la fase:**

3. Iniciar una sesión de voz real, con auriculares puestos. Hablar
   normalmente varias veces seguidas.
4. **Primer chequeo crítico**: ¿el servidor sigue mandando mensajes? Mirar
   la consola — si después de conectar no aparece NINGUNA transcripción ni
   respuesta (el mismo síntoma exacto de la Fase 06), esta fase se
   considera fallida ahí mismo. Revertir el cambio inmediatamente
   (comentar/quitar `realtime_input_config` de nuevo) y documentar en
   `plans/ERRORES.md` que `prefix_padding_ms` aislado, con este modelo y
   esta cuenta, también deja el servidor mudo — dato real, no hipótesis.
5. Si el servidor sigue respondiendo con normalidad: hablar varias
   oraciones largas con pausas naturales dentro (como al pensar qué decir)
   y confirmar que Jarvis NO se corta a mitad de una idea por esas pausas.
6. Confirmar si el problema reportado ("se interrumpe cuando no dije nada")
   mejoró, sigue igual, o empeoró. Cualquiera de los tres resultados es
   información válida — anotarlo tal cual en el reporte final, no forzar
   una conclusión positiva.

## Entregable final de la fase

- `realtime_input_config` con `prefix_padding_ms=300` en `voice_engine.py`,
  aislado, sin ningún otro campo de VAD.
- Comentario actualizado explicando qué se agregó y por qué, dejando rastro
  para quien siga con `silence_duration_ms` en una fase futura.
- Resultado real de la prueba manual (punto 3-6) documentado en el reporte
  de la fase — **si el resultado es negativo (servidor mudo o sin mejora),
  la fase NO se aprueba tal cual quedó, se revierte el cambio de código y
  se documenta el hallazgo real en `plans/ERRORES.md`**. Un resultado
  negativo bien documentado es un entregable válido — es exactamente el
  dato que le faltaba a la entrada de Fase 06.
- Marcar `- [x] Fase 14` en `plans/README.md` **solo si el servidor siguió
  funcionando con normalidad** (con o sin mejora del síntoma original —
  eso es un ajuste fino a seguir probando, lo que no puede pasar es que se
  vuelva a romper la sesión entera).
