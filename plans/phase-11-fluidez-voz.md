# Fase 11 — Fluidez de voz: matar la mordida de 600ms y devolver el barge-in

## Objetivo

Arreglar los dos bugs de fluidez más reportados por el usuario: "las
palabras me llegan cortadas" y "no puedo interrumpir a Jarvis mientras
habla". Los dos tienen la misma causa raíz: `_enviar_audio` reemplaza el
audio del mic por silencio digital mientras `self.hablando` es `True`, y
`hablando` sigue `True` hasta 600ms después de que Jarvis terminó de
sonar (`_UMBRAL_HABLANDO_S`). Ese silencio artificial es lo que corta las
primeras palabras del usuario y lo que mata el barge-in (el VAD del
servidor nunca ve audio real mientras Jarvis habla).

Referencia: `plans/INVESTIGACION-2026-07-27-voz-tools-ui.md`, hallazgos
#1 y #2 del resumen ejecutivo, y secciones 2.2 y 3.1.

## Contexto

Depende de la **Fase 06** (`voice_engine.py` ya existe con la sesión Live
funcionando) y de la **Fase 01** (`config.py`, `DEFAULTS`).

Código actual relevante:

- `Jarvis/app/voice_engine.py:48` — `_UMBRAL_HABLANDO_S = 0.6`.
- `Jarvis/app/voice_engine.py:70-79` — propiedad `hablando`: usada para
  el estado de `/api/estado` (Fase 09, panel ASCII) **y** para decidir el
  mute del mic en `_enviar_audio`. Esta fase separa esos dos usos —
  `/api/estado` sigue leyendo `hablando` tal cual, el mute de audio pasa a
  tener su propio criterio.
- `Jarvis/app/voice_engine.py:241-269` — `_enviar_audio`: el mute total
  vive en las líneas 264-265 (`if self.hablando: chunk = b"\x00" * len(chunk)`),
  con una nota `ponytail` ya existente explicando por qué se muteaba
  entero (eco parlante+mic) y anticipando el flag de auriculares.

Por qué no se hizo antes: sin cancelación de eco real, silenciar el mic
mientras Jarvis habla evita que el sistema se escuche a sí mismo. La
solución no es sacar el mute sin más — es condicionarlo a si el usuario
usa auriculares (sin eco posible → sin necesidad de mute) o, si no los
usa, reemplazar el mute total por un gate de energía que deje pasar audio
real cuando alguien habla fuerte encima del eco.

## Alcance de esta fase

### 1. Config: flag de auriculares

En `Jarvis/app/config.py`, agregar a `DEFAULTS`:

```python
"usar_auriculares": False,
```

No hace falta endpoint nuevo — `POST /api/config` (`server.py:118`) ya
persiste cualquier clave vía `config.save_settings(datos)`.

### 2. Selector en la UI

En el modal de Configuración (`Jarvis/assets/index.html` / `app.js`,
donde ya vive el selector de voz de la Fase 08), agregar un checkbox
"Uso auriculares (sin eco)" que lea/escriba `usar_auriculares` con el
mismo patrón que el resto de los campos del modal — cargar de
`GET /api/config` al abrir, mandar a `POST /api/config` al guardar.

### 3. `_enviar_audio`: desacoplar el mute de `hablando`

En `Jarvis/app/voice_engine.py`, reemplazar la condición de las líneas
264-265 por lógica propia, no ligada a `_UMBRAL_HABLANDO_S`:

- **Si `usar_auriculares` es `True`**: nunca mutear. Mandar el chunk del
  mic tal cual, siempre. Con auriculares no hay eco posible, así que el
  VAD del servidor puede detectar al usuario interrumpiendo en cualquier
  momento (el manejo de `server_content.interrupted` ya existe en
  `_recibir`, `voice_engine.py:296` — solo estaba muerto por falta de
  audio real que lo dispare).
- **Si `usar_auriculares` es `False`** (default): en vez de mute binario,
  gate por energía. Calcular RMS del chunk PCM16 entrante; si supera un
  umbral (`_UMBRAL_RMS_ECO`, constante nueva, punto de partida sugerido
  ~500 sobre escala int16 — **requiere calibrarse escuchando de verdad**,
  no dar por bueno el número de partida) dejar pasar el audio real
  (usuario hablando fuerte encima del eco = quiere interrumpir); si no lo
  supera, mandar silencio como hasta ahora. Sin dependencias nuevas
  (`audioop.rms` de la librería estándar, o un cálculo manual con
  `array`/`struct` si `audioop` no está disponible en la versión de
  Python del proyecto — confirmar al implementar).

El criterio de mute deja de leer `self.hablando` directamente; puede
seguir usando el timestamp `_ultimo_audio_ts` si hace falta saber "recién
terminó de sonar", pero el punto central es que **el RMS manda por
encima del timer**: si el usuario grita una palabra en medio de esos
600ms, tiene que pasar.

**No tocar** `_UMBRAL_HABLANDO_S` ni la propiedad `hablando` en sí —
siguen siendo correctos para `/api/estado` y `procesando` (Fase 09), que
es un uso distinto y no debe romperse.

### 4. Logging para poder verificar el cambio de verdad

Agregar un log puntual (mismo formato `[VoiceEngine][hh:mm:ss] ...` que
ya usa el archivo) cuando el gate deja pasar audio real durante el
período de mute (ej. `"barge-in detectado, RMS=<valor>"`), para poder
confirmar en consola que el gate está funcionando sin depender solo de
"se sintió mejor".

## Fuera de alcance

- **AEC real** (`speexdsp`, `webrtc-audio-processing`, `pyaec`) — es la
  solución correcta a largo plazo pero es una dependencia nativa nueva,
  fuera del alcance de esta fase (ver sección 2.2, opción 3 de la
  investigación).
- **Tocar `realtime_input_config` / VAD del servidor** — eso es la
  Fase 13, deliberadamente separada para no mezclar variables (la Fase 06
  ya rompió una sesión combinando cambios de VAD).
- **Function calling asíncrono / `scheduling`** — Fase 12.
- **Reproducir el silencio con fade en vez de corte duro** — micro-ajuste
  de audio que no ataca ninguno de los dos síntomas reportados, no vale
  la pena en esta fase.

## Verificación

Manual, con la app real (esto no se valida con un assert):

1. Con `usar_auriculares: false` (default) y parlante+mic del equipo:
   hablarle a Jarvis, dejar que responda, e interrumpirlo a mitad de
   frase hablando fuerte. Confirmar en consola que aparece el log de
   barge-in y que Jarvis efectivamente para de hablar
   (`server_content.interrupted`).
2. Mismo escenario: responderle a Jarvis apenas termina de hablar (sin
   pausa). Confirmar que la primera palabra ya no se pierde ni se corta
   en la transcripción.
3. Activar `usar_auriculares: true` desde el modal, reiniciar sesión de
   voz, repetir 1 y 2 con auriculares puestos — confirmar que el barge-in
   es inmediato (sin depender del gate de RMS).
4. Confirmar que el estado del panel ASCII (Fase 09: inactivo /
   escuchando / hablando / procesando) sigue funcionando igual que antes
   — este cambio no debe alterar `/api/estado`.
5. Sesión larga de ida y vuelta (5+ turnos) sin que el sistema entre en
   bucle de "se escucha a sí mismo" — si el umbral de RMS quedó
   demasiado sensible, va a pasar esto; si pasa, subir
   `_UMBRAL_RMS_ECO` y volver a probar.

## Entregable final de la fase

- `usar_auriculares` en `config.py` (`DEFAULTS`) + checkbox en el modal
  de Configuración.
- `_enviar_audio` con mute condicionado a auriculares, y gate de energía
  (no mute binario) cuando no hay auriculares.
- Log de barge-in detectado durante el período de mute.
- Marcar `- [x] Fase 11` en `plans/README.md`.
