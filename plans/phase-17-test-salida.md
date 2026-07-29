# Fase 17 — Probador de salida (parlante/auriculares): tono audible real

## Objetivo

El usuario tuvo una sesión donde Jarvis respondió (transcripción y texto
correctos) pero **no emitió sonido**. `stream_out.write()` puede "funcionar"
sin tirar excepción y aun así no sonar nada (ya pasó con el dispositivo
virtual de FxSound) — no hay forma de saber si un `speaker_device_index`
realmente suena sin escucharlo. Mismo problema que resolvió la Fase 13 para
el micrófono, ahora para la salida.

## Contexto

Depende de la **Fase 01** (`config.py`, `speaker_device_index`) y **Fase 13**
(mismo patrón de panel de prueba en el modal de Configuración, mismo estilo
de endpoint). Reutiliza `_SAMPLE_RATE_OUT` de `voice_engine.py` — la prueba
tiene que sonar exactamente a la tasa que usa la sesión real, para que un
error de tasa inválida (visto en vivo, `PaErrorCode -9997`) aparezca acá y
no recién en una sesión de voz real.

## Alcance de esta fase

### 1. Backend: reproducir un tono corto y audible

En `server.py`, un endpoint nuevo:

- `POST /api/speaker-test` — recibe `{"speaker_device_index": N}` (opcional,
  default al configurado). Genera un tono corto (ej. onda seno ~440-660Hz,
  0.6-0.8s, PCM16 mono a `_SAMPLE_RATE_OUT`) en memoria (sin dependencias
  nuevas — `math.sin` + `struct.pack`, ya se usa `math` en este archivo) y lo
  reproduce con `sd.RawOutputStream(device=..., samplerate=_SAMPLE_RATE_OUT)`.
  Devuelve `{"ok": true}` si abrió y escribió sin excepción, o
  `{"ok": false, "error": "..."}` si PortAudio falló (ej. tasa inválida) —
  esto SÍ hay que devolverlo a la UI, a diferencia del error de la sesión de
  voz real que hoy solo se ve en la consola del proceso.
- Igual que el mic-test: rechazar si hay una sesión de voz activa
  (`{"ok": false, "error": "Detené la sesión de voz antes de probar la
  salida, señor."}`), mismo motivo (dos streams compitiendo por el mismo
  dispositivo).
- No hace falta estado tipo `_mic_test` (activo/nivel) — es un disparo único
  que bloquea el request hasta que termina de sonar (menos de 1 segundo), no
  un stream continuo. Más simple que el mic-test a propósito.

### 2. Frontend: botón en el modal, junto al selector de salida

- Botón "Probar salida" (mismo patrón visual que el de mic-test).
- Al click, `POST /api/speaker-test` con el `speaker_device_index`
  actualmente seleccionado en el modal (aunque todavía no se haya guardado
  — para poder probar antes de confirmar el cambio).
- Mostrar el resultado: si `ok`, un mensaje tipo "¿Escuchaste el tono?" (no
  hay forma de saberlo desde el backend, es honesto pedírselo al usuario);
  si `ok: false`, mostrar el error real de PortAudio tal cual — eso es
  información nueva que hoy se pierde.

## Fuera de alcance

- Cualquier detección automática de "sonó de verdad" — es imposible sin
  hardware adicional (micrófono captando el parlante), y no vale la pena.
- Tocar el flujo de audio de la sesión de voz real (`voice_engine.py`) —
  esta fase es un stream aislado, igual que el mic-test.
- Selector de volumen o forma de onda distinta — un tono simple alcanza.

## Verificación

1. `POST /api/speaker-test` con el índice de un dispositivo real (ej. 5)
   devuelve `{"ok": true}` y se escucha un tono corto.
2. `POST /api/speaker-test` con un índice WASAPI que ya sabemos que falla a
   esta tasa (ej. 14) devuelve `{"ok": false, "error": "...Invalid sample
   rate..."}` sin tirar 500 ni colgar el server.
3. `POST /api/speaker-test` con una sesión de voz activa devuelve el
   rechazo explícito, sin abrir un segundo stream.
4. Manual: click en "Probar salida" en el modal con distintos dispositivos
   del selector, confirmar que el mensaje coincide con lo que realmente se
   escucha.

## Entregable final de la fase

- `POST /api/speaker-test` en `server.py`, con guard contra sesión activa y
  reporte real de errores de PortAudio.
- Botón "Probar salida" en el modal de Configuración.
- Marcar `- [x] Fase 17` en `plans/README.md`.
