# Fase 13 — Probador de micrófono: nivel en vivo, ¿me detecta?

## Objetivo

Un panel en el modal de Configuración que muestre, en vivo, el nivel de
audio que está captando el micrófono seleccionado — para que el usuario
pueda confirmar "sí, me está escuchando" sin tener que arrancar una sesión
completa de voz (que gasta cuota y depende de la red). Sirve además como
herramienta de diagnóstico real para calibrar `_UMBRAL_RMS_ECO` (Fase 11) y,
más adelante, el VAD (Fase 14) — exactamente el principio de "instrumentar
antes de cambiar" que ya sigue el resto del plan.

Pedido explícito del usuario: un lugar para ver decibeles/nivel y probar si
el micrófono detecta la voz desde donde está hablando.

**Alcance deliberadamente chico:** un medidor de nivel (barra que sube y
baja con el volumen), no un espectro de frecuencias completo (FFT, barras
por banda). Lo segundo es mucho más código (`numpy.fft`, canvas, escalado
logarítmico) para responder la misma pregunta ("¿me detecta?") que ya
responde un medidor simple. Si más adelante hace falta ver espectro de
verdad (para diagnosticar ruido de fondo por frecuencia, por ejemplo), es
una fase aparte.

## Contexto

Depende de la **Fase 01** (`config.py`, `mic_device_index`) y **Fase 08**
(modal de Configuración en `index.html`/`app.js`). Reutiliza:

- `_rms_pcm16()` (`Jarvis/app/voice_engine.py:70-73`, agregada en la Fase
  11) — cálculo de RMS de un chunk PCM16 vía `audioop.rms`, ya probado.
  Importarla desde ahí (`from app.voice_engine import _rms_pcm16`), no
  duplicar la función.
- El patrón de `_voz_cache` / `_pip` en `server.py` (diccionario module-level
  con la referencia al recurso vivo) para el estado del test de mic.
- El patrón de `/api/audio-devices` (`server.py:165-192`) para los índices
  reales de PortAudio — el selector de mic ya existente en el modal.

**Conflicto a evitar, importante:** el test de mic abre su propio
`sounddevice.RawInputStream` sobre el mismo dispositivo que usaría una
sesión de voz real. Si el usuario arranca el test mientras la sesión Live
está activa (`VoiceEngine.activo`), hay dos streams compitiendo por el mismo
hardware — en Windows esto puede fallar en abrir el segundo, o directamente
robarle el audio al primero. **El test debe rechazar arrancar si hay una
sesión de voz activa**, con un mensaje claro en la UI.

## Alcance de esta fase

### 1. Backend: captura de nivel en un thread aparte

En `Jarvis/app/server.py`, agregar estado module-level para el test:

```python
_mic_test = {"activo": False, "nivel": 0.0, "stream": None, "detener": None}
```

- `POST /api/mic-test/iniciar` — recibe `{"mic_device_index": N}` (o usa el
  configurado si no se manda). Si `_voz_cache["motor"]` está activo,
  responde error explícito ("Detené la sesión de voz antes de probar el
  micrófono, señor" o similar, en JSON, sin 500). Si no, abre un
  `sd.RawInputStream` con un callback que calcula `_rms_pcm16(bytes(indata))`
  y lo guarda en `_mic_test["nivel"]` (float, sin normalizar todavía).
- `POST /api/mic-test/detener` — para el stream, limpia el estado.
- `GET /api/mic-test/nivel` — devuelve `{"activo": bool, "nivel": float}`.
  El front hace polling de este endpoint mientras el panel está abierto
  (mismo patrón que `/api/estado`, cada ~150-200ms para que se sienta en
  vivo — más rápido que el resto de los pollings porque acá la
  responsividad es el punto).

Normalización a 0-100 para la barra: se puede hacer en el backend o en el
frontend, decisión libre de quien implemente — pero un RMS crudo de PCM16
va de 0 a ~32767; una escala razonable es `min(100, nivel / 300)` o similar
(ajustar por prueba real, dejar como constante nombrada, no un número
mágico suelto en medio del código).

### 2. Frontend: panel en el modal de Configuración

En el modal existente (`Jarvis/assets/index.html`, junto al selector de
mic), agregar una sección "Probar micrófono":

- Botón "Probar" / "Detener" (toggle, mismo patrón visual que `#btnVoz` o
  `#btnPip`).
- Una barra de nivel simple: un `<div>` con el ancho o alto controlado por
  JS según el `nivel` recibido del polling (nada de canvas ni librerías de
  gráficos — un `div` con `background` y `width` dinámico alcanza).
- Un indicador de texto simple: "Sin señal" / "Te escucho" — que cambie
  cuando el nivel cruce un umbral (puede ser el mismo `_UMBRAL_RMS_ECO`
  del backend expuesto vía el JSON, o una constante propia del frontend
  — documentar cuál se usó y por qué).
- Si el usuario cierra el modal o hace click en "Detener" sin haberlo hecho
  antes, el frontend debe llamar `POST /api/mic-test/detener` — no dejar el
  stream abierto huérfano en el backend.

### 3. Estética

Respetar la guía visual del proyecto (Watch Dogs 2, negro/blanco, trazo
grueso, monoespaciado) — la barra de nivel es blanco sobre negro, sin
colores de acento (nada de verde/rojo tipo semáforo; usar intensidad o
patrón, no color, para distinguir "sin señal" de "con señal").

## Fuera de alcance

- **Espectro de frecuencias / FFT** — ver la nota en "Objetivo". Si se
  quiere en el futuro, es una fase aparte.
- **Grabar o guardar audio de la prueba** — el test es solo nivel en vivo,
  no hay ningún archivo de audio que persista.
- **Usarlo para calibrar automáticamente `_UMBRAL_RMS_ECO`** — el panel
  ayuda a un humano a decidir el número mirando la barra, pero no escribe
  ningún valor de configuración por su cuenta. Ajustar la constante en
  código sigue siendo manual, fuera de esta fase.
- **Tocar `voice_engine.py`** más allá de importar `_rms_pcm16` — ninguna
  lógica de la sesión Live cambia acá.
- **Probar el dispositivo de salida (parlante/auriculares)** — esta fase es
  solo entrada (mic). Un test de salida (reproducir un tono y preguntar "¿lo
  escuchaste?") es una idea razonable pero es otra fase.

## Verificación

Automatizable:

1. Con el mic real conectado, `POST /api/mic-test/iniciar` seguido de
   varios `GET /api/mic-test/nivel` con el usuario en silencio: `nivel`
   debe quedarse bajo/estable.
2. Igual pero hablando fuerte cerca del mic: `nivel` debe subir claramente.
3. `POST /api/mic-test/iniciar` mientras hay una sesión de voz activa: debe
   responder el error explícito, no arrancar un segundo stream, no romper
   la sesión de voz en curso.
4. `POST /api/mic-test/detener` libera el dispositivo (confirmar que
   después se puede iniciar una sesión de voz real sin error de "device
   busy").

Manual:

5. Abrir el modal de Configuración, iniciar el test, hablar y confirmar que
   la barra sube y baja acorde al volumen real de la voz, en tiempo real
   (sin demora perceptible).
6. Cambiar el selector de mic a otro dispositivo (si hay más de uno
   disponible) y confirmar que el test refleja el dispositivo nuevo.
7. Cerrar el modal con el test corriendo, reabrirlo, confirmar que no quedó
   un stream huérfano corriendo en el backend (revisar logs de consola).

## Entregable final de la fase

- `POST /api/mic-test/iniciar`, `POST /api/mic-test/detener`,
  `GET /api/mic-test/nivel` en `server.py`, con el guard contra sesión de
  voz activa.
- Sección "Probar micrófono" en el modal de Configuración: botón
  iniciar/detener, barra de nivel en vivo, indicador de texto simple.
- Reutiliza `_rms_pcm16` de `voice_engine.py`, sin duplicar lógica de RMS.
- Marcar `- [x] Fase 13` en `plans/README.md`.

## Nota sobre el roadmap

Esta fase se inserta **antes** de la fase de VAD que la investigación
llamaba "Fase 13" (reintento controlado de `prefix_padding_ms`) — ese
trabajo se renumera a **Fase 14**. Tiene sentido en ese orden: mejor tener
una forma de ver "¿me está escuchando de verdad?" antes de tocar los
umbrales de detección de voz del servidor.
