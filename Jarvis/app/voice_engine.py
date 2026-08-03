"""voice_engine.py — Motor de voz nativo con la Live API de Gemini.

Sesión bidireccional bajo demanda: mic -> Live API -> altavoz, con la voz
elegida en `config.py`. El function-calling que decide la Live API se
resuelve delegando en `GeminiAgent.ejecutar_tool_directa` (mismo dispatch
que ya usa el agente de texto, no se reimplementa acá).

Deliberadamente desacoplado: ningún otro módulo del proyecto debe importar
nada de este archivo ni saber que la voz viene de Gemini Live — si el día
de mañana se cambia de proveedor de voz, solo se reemplaza esta clase.

Modelo elegido: `gemini-2.5-flash-native-audio-latest`. El nombre con fecha
que traía el plan original (`...-preview-12-2025`) sigue funcionando hoy
(probado con conexión real, no solo `models.list()`) pero un preview con
fecha vence tarde o temprano; el alias `-latest` es el que Google mantiene
apuntando al modelo de audio nativo vigente, mismo criterio que
`gemini-flash-latest` en `gemini_agent.py` (Fase 05, ver `plans/ERRORES.md`).

Formato de audio fijado por la API (no configurable): entrada PCM16 mono
16kHz, salida PCM16 mono 24kHz.
"""
from __future__ import annotations

import asyncio
import queue
import struct
import threading
import time

import sounddevice as sd
from google import genai
from google.genai import types

# ponytail: audioop es stdlib y alcanza para RMS de PCM16; se remueve en
# Python 3.13+ (el proyecto corre en 3.12). Si se actualiza el intérprete y
# esto empieza a fallar, reemplazar por un cálculo manual con `array`.
import audioop

from app import audio_fx, config, persona
from app.gemini_agent import GeminiAgent

# Identidad compartida con el agente de texto (Fase 18, ver persona.py) +
# la instrucción de frase de relleno, específica de voz porque en texto no
# hay espera perceptible por el usuario. Acento regional desactivado por
# ahora (español neutro) -- ver `persona.elegir_acento` para reactivarlo.
def _sistema() -> str:
    return (
        persona.prompt_voz() + "\n\n"
        "Cuando vayas a usar las herramientas buscar_web o open_app, di "
        "antes una frase corta (ej. 'dale, un segundo' o 'ya me fijo') en "
        "vez de quedarte en silencio mientras esperas el resultado."
    )

# Tools NON_BLOCKING (ver gemini_agent.py:_tool_declarations) y el
# `scheduling` con el que responden cuando terminan. `open_app` era
# INTERRUPT en el plan original (Fase 12) pensando en un escaneo lento del
# Menú Inicio — pero con la caché de la misma Fase 12 resuelve casi
# instantáneo, y INTERRUPT corta a Jarvis A MITAD DE LA FRASE DE RELLENO
# ("dale, un segundo...") casi siempre, lo cual se sentía y se logueaba
# como "interrumpido por el usuario" sin que el usuario dijera nada (visto
# en vivo, Fase 14). WHEN_IDLE deja terminar la frase corta y responde
# ahí — con resolución casi instantánea la diferencia percibida es mínima
# y no hay corte falso.
_TOOLS_NO_BLOQUEANTES = {
    "buscar_web": types.FunctionResponseScheduling.WHEN_IDLE,
    "open_app": types.FunctionResponseScheduling.WHEN_IDLE,
    # `musica` hace scraping de red a YouTube (~0.9s medido) antes de poder
    # abrir el navegador — bloquear `_recibir_turno` ese tiempo entero
    # colgaba el resto del turno de voz (mismo motivo que buscar_web/
    # open_app). `tareas` y `recordatorios` NO están acá: son lectura/
    # escritura de JSON local (<1ms medido), agregarles NON_BLOCKING solo
    # metería latencia perceptible sin ganancia real.
    "musica": types.FunctionResponseScheduling.WHEN_IDLE,
}

_SAMPLE_RATE_IN = 16000
_SAMPLE_RATE_OUT = 24000
_CHUNK_MS = 30

# Punto de partida sugerido por el plan de Fase 11 si el usuario nunca tocó
# `umbral_rms_eco` en config — leído en caliente al conectar (ver
# `_UMBRAL_RMS_ECO_DEFAULT` abajo). Calibrar de oído con el panel de mic-test
# (`/api/mic-test/nivel` ya muestra este umbral superpuesto al nivel real):
# si el barge-in dispara solo (Jarvis se escucha a sí mismo), subir el valor
# en `datos/settings.json`; si no dispara con voz normal fuerte, bajarlo.
_UMBRAL_RMS_ECO_DEFAULT = 500

# Tiempo sin NINGÚN mensaje del servidor mientras hay una respuesta pendiente
# (`_esperando_respuesta=True`) antes de asumir que la sesión quedó muda y
# forzar una reconexión. Sin este watchdog, `_recibir` puede quedar
# esperando un websocket que dejó de mandar CUALQUIER mensaje —ni siquiera
# un error visible— y la app se ve "escuchando" para siempre (visto en vivo,
# ver plans/ERRORES.md). No se usa un timeout de silencio genérico porque el
# usuario callado pensando es un estado normal y frecuente; el watchdog solo
# actúa cuando YA había un turno en curso.
_TIMEOUT_PROCESANDO_S = 15.0


def _rms_pcm16(chunk: bytes) -> float:
    if not chunk:
        return 0.0
    return audioop.rms(chunk, 2)


def _en_ventana_de_eco(cola_salida: "queue.Queue | None", ultimo_audio_ts: float,
                        ventana_s: float, ahora: float) -> bool:
    if cola_salida is not None and not cola_salida.empty():
        return True
    return (ahora - ultimo_audio_ts) < ventana_s


class VoiceEngine:
    # native-audio-latest ignora el `parameters_json_schema` de las tools y
    # manda nombres de campo inventados (ej. `nombre`/`fecha_hora` en vez de
    # `query`/`when`) — confirmado probando las 4 tools reales contra la API.
    # 3.1-flash-live-preview respeta el schema en el mismo test.
    MODEL = "gemini-3.1-flash-live-preview"
    _UMBRAL_HABLANDO_S = 0.6
    # Ventana propia del gate de eco de `_enviar_audio`, separada a propósito
    # de `_UMBRAL_HABLANDO_S` (que es del estado de UI, Fase 09) — la Fase 11
    # pide que el mute del mic no dependa de `hablando` directamente.
    _VENTANA_MUTEO_S = 0.6

    # Reconexiones seguidas (cada una duró menos de _DURACION_SANA_S) antes
    # de rendirse y dejar la sesión caída con `ultimo_error` visible. Sin
    # este techo, un fallo persistente (red caída, API con problemas)
    # reconectaría infinitamente en silencio.
    _MAX_RECONEXIONES_SEGUIDAS = 5
    _DURACION_SANA_S = 30.0

    def __init__(self, api_key: str, voice: str, agente: GeminiAgent):
        self._client = genai.Client(api_key=api_key)
        self.voice = voice
        self.agente = agente
        self._thread: threading.Thread | None = None
        self._detener_flag: threading.Event | None = None
        self._detenido_por_usuario = False
        self._activo = False
        self.ultimo_error: str | None = None
        self._ultimo_audio_ts = 0.0
        self._esperando_respuesta = False
        self._buf_usuario = ""
        self._buf_jarvis = ""
        self.transcripciones: list[dict] = []  # [{"quien": "usuario"|"jarvis", "texto": ...}]
        self._cola_salida: queue.Queue | None = None
        # Referencias a las tasks de tools NON_BLOCKING en vuelo: sin esto el
        # garbage collector puede recolectar una task "fire and forget" a
        # mitad de camino (error clásico de asyncio, ver plans/ERRORES.md).
        self._tools_pendientes: list[asyncio.Task] = []
        # Handle de `session_resumption`: si el servidor lo marca `resumable`
        # (ver `_recibir_turno`), reconectar con este handle recupera el
        # contexto de la conversación en vez de arrancar en blanco — sin
        # esto cada corte (15 min de límite duro, GoAway, red) perdía toda
        # la charla previa. `None` = sesión nueva sin historial que resumir.
        self._handle_resumption: str | None = None
        # Timestamp del último mensaje CUALQUIERA del servidor (no solo los
        # que el código interpreta) — lo usa el watchdog de `_sesion_async`
        # para detectar una sesión que dejó de responder (ver
        # `_TIMEOUT_PROCESANDO_S`).
        self._ultimo_evento_ts = 0.0

    @property
    def activo(self) -> bool:
        return self._activo

    @property
    def hablando(self) -> bool:
        """True mientras queda audio de Jarvis por reproducir (o terminó de
        sonar hace menos de _UMBRAL_HABLANDO_S) — usado por `/api/estado`
        (Fase 09) para distinguir "escuchando" de "hablando". Desde la Fase
        11, `_enviar_audio` usa su propio criterio (`_ventana_de_eco_activa`)
        en vez de este, para no atar el gate de eco al timer de la UI."""
        if not self._activo:
            return False
        if self._cola_salida is not None and not self._cola_salida.empty():
            return True
        return (time.monotonic() - self._ultimo_audio_ts) < self._UMBRAL_HABLANDO_S

    def _ventana_de_eco_activa(self) -> bool:
        return _en_ventana_de_eco(
            self._cola_salida, self._ultimo_audio_ts, self._VENTANA_MUTEO_S, time.monotonic()
        )

    @property
    def procesando(self) -> bool:
        """True desde que llegó una transcripción de lo que dijo el usuario
        hasta que empieza a llegar audio/texto de la respuesta — cubre el
        hueco entre "terminé de hablar" y "Jarvis ya está respondiendo" que
        el panel (Fase 09) no podía mostrar antes (reportado por el usuario
        probando la app real: "no hay nada que me diga que se está
        procesando")."""
        return self._activo and self._esperando_respuesta and not self.hablando

    def _cerrar_turno_usuario(self) -> None:
        if self._buf_usuario.strip():
            print(f"[VoiceEngine][{time.strftime('%H:%M:%S')}] usuario dijo: {self._buf_usuario.strip()!r}")
            self.transcripciones.append({"quien": "usuario", "texto": self._buf_usuario.strip()})
        self._buf_usuario = ""

    def _cerrar_turno_jarvis(self) -> None:
        if self._buf_jarvis.strip():
            print(f"[VoiceEngine][{time.strftime('%H:%M:%S')}] jarvis dijo: {self._buf_jarvis.strip()!r}")
            self.transcripciones.append({"quien": "jarvis", "texto": self._buf_jarvis.strip()})
        self._buf_jarvis = ""
        self._esperando_respuesta = False

    def iniciar_sesion(self) -> None:
        if self._activo:
            return
        self.ultimo_error = None
        self._detener_flag = threading.Event()
        self._detenido_por_usuario = False
        self._esperando_respuesta = False
        self._buf_usuario = ""
        self._buf_jarvis = ""
        self.transcripciones = []
        self._handle_resumption = None
        self._activo = True
        self._thread = threading.Thread(target=self._correr_en_thread, daemon=True)
        self._thread.start()

    def detener_sesion(self) -> None:
        if not self._activo or not self._detener_flag:
            return
        self._detenido_por_usuario = True
        self._detener_flag.set()
        if self._thread:
            self._thread.join(timeout=10)
        self._activo = False

    def _correr_en_thread(self) -> None:
        """Loop de reconexión: una sesión Live cortada (límite de 15 min,
        GoAway, red, watchdog) no es un error terminal — se reconecta sola
        con `_handle_resumption` si el servidor lo dio por resumible. Solo
        para de reconectar si el usuario apretó "detener" o si varias
        reconexiones seguidas mueren rápido (fallo persistente, no un corte
        aislado)."""
        intentos_fallidos = 0
        while not self._detener_flag.is_set():
            inicio = time.monotonic()
            try:
                asyncio.run(self._sesion_async())
            except Exception as e:
                self.ultimo_error = str(e)
                print(f"[VoiceEngine][{time.strftime('%H:%M:%S')}] Error: {e}")

            if self._detenido_por_usuario or self._detener_flag.is_set():
                break

            duracion = time.monotonic() - inicio
            intentos_fallidos = 0 if duracion > self._DURACION_SANA_S else intentos_fallidos + 1
            if intentos_fallidos > self._MAX_RECONEXIONES_SEGUIDAS:
                self.ultimo_error = self.ultimo_error or "La sesión de voz se cortó repetidamente."
                print(f"[VoiceEngine][{time.strftime('%H:%M:%S')}] "
                      f"{self._MAX_RECONEXIONES_SEGUIDAS} reconexiones seguidas fallaron rápido, abandono.")
                break

            espera = min(1.0 * intentos_fallidos, 5.0)
            print(f"[VoiceEngine][{time.strftime('%H:%M:%S')}] sesión cortada tras {duracion:.1f}s, "
                  f"reconectando en {espera:.1f}s (handle={'sí' if self._handle_resumption else 'no'})...")
            self._detener_flag.wait(espera)

        self._activo = False

    async def _sesion_async(self) -> None:
        live_config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            tools=[self.agente.tools],
            system_instruction=_sistema(),
            # `language_code` PROBADO y RECHAZADO por la API en vivo:
            # "Unsupported language code 'es-419' for model
            # models/gemini-2.5-flash-native-audio-latest" (1007, ver
            # plans/ERRORES.md). No hay código regional colombiano
            # documentado para este modelo — el acento se controla SOLO por
            # léxico en el prompt (persona.py), no por este campo. No volver
            # a probar otro `language_code` sin confirmar antes en la doc
            # oficial de idiomas soportados por la Live API.
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self.voice)
                ),
            ),
            # Sin esto, la Live API no manda ningún texto — solo audio — y no
            # había forma de mostrar en pantalla lo que el usuario dijo ni lo
            # que Jarvis respondió (reportado probando la app real).
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            # Fase 06 (ver plans/ERRORES.md) probó `realtime_input_config` con
            # sensibilidades explícitas y `silence_duration_ms` bajo, y el
            # servidor dejó de mandar CUALQUIER mensaje. Fase 14 agregó
            # `prefix_padding_ms` aislado y sobrevivió (no es el campo en sí
            # lo que rompía todo). Fase 15 agrega la SEGUNDA variable, con el
            # usuario confirmando en vivo que sin esto el servidor corta su
            # turno antes de que termine de hablar (silencios/pausas para
            # pensar se leían como "ya terminó"). `silence_duration_ms=800`
            # es el techo del rango que la doc oficial recomienda (500-800ms;
            # por debajo de 500 fragmenta el habla) — se elige el techo,
            # no el piso, porque el síntoma reportado es "corta corto", no
            # "tarda en responder". NO tocar sensibilidades
            # (start/end_of_speech_sensitivity) todavía — sigue siendo una
            # variable por vez.
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    prefix_padding_ms=300,
                    silence_duration_ms=800,
                ),
            ),
            # Handle de la sesión anterior si `_recibir_turno` guardó uno
            # `resumable` — reconecta con el contexto de la charla en vez de
            # arrancar en blanco. `None` en la primera conexión. Ver
            # INVESTIGACION-2026-07-27, sección de sesión (ítem 16): esto es
            # lo que evita el corte duro a los 15 minutos.
            session_resumption=types.SessionResumptionConfig(handle=self._handle_resumption),
            # Ventana deslizante del lado del servidor: descarta los turnos
            # más viejos al pasar `trigger_tokens` en vez de cortar la sesión
            # entera cuando se llena la ventana de contexto (128k, ~25
            # tokens/s de audio). `target_tokens=4_000` es el valor de
            # ejemplo de la doc oficial — implica olvidar turnos viejos en
            # sesiones muy largas, aceptable frente a la alternativa (sesión
            # cortada del todo).
            context_window_compression=types.ContextWindowCompressionConfig(
                trigger_tokens=100_000,
                sliding_window=types.SlidingWindow(target_tokens=4_000),
            ),
        )

        mic_idx = config.get("mic_device_index", -1)
        speaker_idx = config.get("speaker_device_index", -1)
        # Leído una sola vez al conectar, mismo patrón que mic/speaker arriba:
        # cambiar el checkbox en caliente requiere reiniciar la sesión de voz.
        usar_auriculares = bool(config.get("usar_auriculares", False))
        # `FiltroVenom` = pitch-down real + capa secundaria + FiltroUltratumba
        # (ver plans/INVESTIGACION-2026-07-30-voz-venom.md). Mismo checkbox
        # que antes (`voz_ultratumba`) — sigue siendo "el filtro experimental
        # de voz", ahora con pitch grave real en vez de solo distorsión.
        efecto_ultratumba = (
            audio_fx.FiltroVenom(_SAMPLE_RATE_OUT)
            if config.get("voz_ultratumba", False) else None
        )

        # Señal de "esta conexión particular debe cerrarse y `_correr_en_thread`
        # debe reconectar" — separada de `_detener_flag` (que es "el usuario
        # apretó detener, no reconectar nunca más"). Un watchdog o un GoAway
        # del servidor setean esto pero NO deben terminar la sesión entera.
        reconectar = asyncio.Event()

        async with self._client.aio.live.connect(model=self.MODEL, config=live_config) as session:
            print(f"[VoiceEngine][{time.strftime('%H:%M:%S')}] sesion conectada, modelo={self.MODEL}, "
                  f"reanudando={'sí' if self._handle_resumption else 'no'}")
            self._ultimo_evento_ts = time.monotonic()
            loop = asyncio.get_running_loop()
            cola_in: asyncio.Queue[bytes] = asyncio.Queue()

            def _callback_in(indata, frames, time_info, status):
                loop.call_soon_threadsafe(cola_in.put_nowait, bytes(indata))

            stream_in = sd.RawInputStream(
                samplerate=_SAMPLE_RATE_IN, channels=1, dtype="int16",
                blocksize=int(_SAMPLE_RATE_IN * _CHUNK_MS / 1000),
                device=None if mic_idx == -1 else mic_idx,
                callback=_callback_in,
            )
            stream_out = sd.RawOutputStream(
                samplerate=_SAMPLE_RATE_OUT, channels=1, dtype="int16",
                device=None if speaker_idx == -1 else speaker_idx,
            )
            stream_in.start()
            stream_out.start()

            # La reproducción va por un hilo aparte con su propia cola:
            # `stream_out.write()` es BLOQUEANTE (espera a que suene el audio),
            # y hacerlo dentro de `_recibir` dejaba a esa tarea sin leer
            # mensajes nuevos durante toda la respuesta de Jarvis — de ahí
            # que la sesión "se quedara escuchando" y no volviera a responder.
            self._cola_salida = queue.Queue()
            fin_reproductor = threading.Event()
            hilo_out = threading.Thread(
                target=self._reproducir_loop,
                args=(stream_out, self._cola_salida, fin_reproductor, efecto_ultratumba),
                daemon=True,
            )
            hilo_out.start()

            enviar_task = asyncio.create_task(self._enviar_audio(session, cola_in, usar_auriculares))
            recibir_task = asyncio.create_task(self._recibir(session, loop, reconectar))
            try:
                while not self._detener_flag.is_set() and not reconectar.is_set():
                    # Si alguna de las dos tareas murió (excepción propia o
                    # corte del servidor), no tiene sentido seguir esta
                    # conexión: se marca para reconectar. Antes esto ponía
                    # `_detener_flag` directo y mataba la sesión entera en
                    # vez de solo esta conexión.
                    for t, nombre in ((enviar_task, "enviar"), (recibir_task, "recibir")):
                        if t.done():
                            exc = t.exception()
                            msg = f"tarea '{nombre}' terminó" + (f": {exc!r}" if exc else " sin error")
                            print(f"[VoiceEngine][{time.strftime('%H:%M:%S')}] {msg}")
                            self.ultimo_error = msg
                            reconectar.set()

                    # Watchdog: hay un turno del usuario pendiente de
                    # respuesta y no llegó NINGÚN mensaje del servidor (ni
                    # siquiera uno que el código no entienda) en más de
                    # `_TIMEOUT_PROCESANDO_S` — la sesión quedó muda sin
                    # error visible (ver plans/ERRORES.md, "se quedó
                    # procesando 80 segundos"). No dispara con el usuario
                    # simplemente en silencio porque exige `_esperando_respuesta`.
                    if (self._esperando_respuesta and not self.hablando
                            and time.monotonic() - self._ultimo_evento_ts > _TIMEOUT_PROCESANDO_S):
                        msg = (f"sin respuesta del servidor por más de "
                               f"{_TIMEOUT_PROCESANDO_S:.0f}s con un turno pendiente")
                        print(f"[VoiceEngine][{time.strftime('%H:%M:%S')}] watchdog: {msg}, reconectando")
                        self.ultimo_error = msg
                        reconectar.set()

                    await asyncio.sleep(0.2)
            finally:
                enviar_task.cancel()
                recibir_task.cancel()
                for t in list(self._tools_pendientes):
                    t.cancel()
                for t in (enviar_task, recibir_task, *self._tools_pendientes):
                    try:
                        await t
                    except (asyncio.CancelledError, Exception):
                        pass
                self._tools_pendientes.clear()
                fin_reproductor.set()
                self._cola_salida = None
                hilo_out.join(timeout=2)
                stream_in.stop()
                stream_in.close()
                stream_out.stop()
                stream_out.close()

    def _reproducir_loop(self, stream_out, cola: "queue.Queue", fin: threading.Event, efecto=None) -> None:
        while not fin.is_set():
            try:
                datos = cola.get(timeout=0.2)
            except queue.Empty:
                continue
            if datos is None:
                continue
            try:
                if efecto is not None:
                    datos = efecto.procesar(datos)
                stream_out.write(datos)
                self._ultimo_audio_ts = time.monotonic()
            except Exception as e:
                print(f"[VoiceEngine][{time.strftime('%H:%M:%S')}] error reproduciendo audio: {e!r}")

    async def _enviar_audio(self, session, cola_in: "asyncio.Queue[bytes]", usar_auriculares: bool) -> None:
        # DEBUG temporal: confirma que el mic realmente está mandando audio
        # (si esto no aparece cada ~1.5s, el problema es el dispositivo de
        # entrada, no la API). Quitar una vez diagnosticado el reporte del
        # usuario de "responde lento / no responde" en voz.
        n = 0
        # Leído una sola vez al conectar, mismo patrón que mic/speaker/
        # auriculares — ajustarlo desde el panel de calibración requiere
        # reiniciar la sesión de voz para que tome efecto.
        umbral_rms_eco = config.get("umbral_rms_eco", _UMBRAL_RMS_ECO_DEFAULT)
        while True:
            chunk = await cola_in.get()
            n += 1
            if n % 50 == 0:
                print(f"[VoiceEngine][{time.strftime('%H:%M:%S')}] mic activo, {n} chunks enviados")
            # Sin cancelación de eco real, el parlante+mic en el mismo
            # dispositivo hacen que Jarvis "se escuche a sí mismo". Se sigue
            # mandando SILENCIO (mismos bytes, en cero) en vez de saltear el
            # envío del todo — cortar el streaming por completo (probado, ver
            # plans/ERRORES.md) rompe el detector de voz del servidor para el
            # resto de la sesión. La diferencia con antes: el mute ya no es
            # binario por `hablando` — con auriculares no hay eco posible
            # (nunca mutea) y sin auriculares un RMS alto (usuario gritando
            # encima del eco) deja pasar el audio real para permitir barge-in.
            if not usar_auriculares and self._ventana_de_eco_activa():
                rms = _rms_pcm16(chunk)
                if rms > umbral_rms_eco:
                    print(f"[VoiceEngine][{time.strftime('%H:%M:%S')}] barge-in detectado, RMS={rms:.0f}")
                else:
                    chunk = b"\x00" * len(chunk)
            await session.send_realtime_input(
                audio=types.Blob(data=chunk, mime_type=f"audio/pcm;rate={_SAMPLE_RATE_IN}")
            )

    async def _recibir(self, session, loop: asyncio.AbstractEventLoop, reconectar: asyncio.Event) -> None:
        # `session.receive()` es un generador POR TURNO: se agota cuando el
        # modelo termina de responder. Sin este `while`, la tarea terminaba
        # después del primer intercambio y no se leía nada más en toda la
        # sesión — de ahí el síntoma "responde una vez y después se queda
        # escuchando para siempre". Hay que volver a pedirlo cada turno.
        while not reconectar.is_set():
            await self._recibir_turno(session, loop, reconectar)

    async def _recibir_turno(self, session, loop: asyncio.AbstractEventLoop, reconectar: asyncio.Event) -> None:
        async for msg in session.receive():
            ts = time.strftime('%H:%M:%S')
            # Cualquier mensaje cuenta como "el servidor sigue vivo" para el
            # watchdog — no solo los tipos que el código de abajo interpreta.
            self._ultimo_evento_ts = time.monotonic()

            if msg.session_resumption_update and msg.session_resumption_update.resumable:
                self._handle_resumption = msg.session_resumption_update.new_handle
                print(f"[VoiceEngine][{ts}] handle de reanudación actualizado")

            if msg.go_away:
                print(f"[VoiceEngine][{ts}] GoAway del servidor, "
                      f"tiempo restante={msg.go_away.time_left}, reconectando")
                reconectar.set()
                return

            # DEBUG temporal: sin esto no hay forma de distinguir "el servidor
            # no manda nada" de "manda algo que el código no interpreta".
            # Quitar cuando la voz esté estable.
            if msg.server_content:
                sc = msg.server_content
                marcas = [k for k in ("model_turn", "turn_complete", "interrupted",
                                      "generation_complete", "input_transcription",
                                      "output_transcription", "waiting_for_input",
                                      "interim_input_transcription")
                          if getattr(sc, k, None)]
                if marcas != ["model_turn"]:
                    print(f"[VoiceEngine][{ts}] server_content: {marcas}")

            if msg.server_content and msg.server_content.interrupted:
                print(f"[VoiceEngine][{ts}] interrumpido por el usuario")
                # ponytail: descarta lo que quede en la cola de reproducción
                # en vez de recortar sample-exacto, alcanza para un barge-in
                # aceptable.
                self._vaciar_cola_salida()

            if msg.server_content and getattr(msg.server_content, "turn_complete", False):
                print(f"[VoiceEngine][{ts}] turno completo")
                self._cerrar_turno_usuario()
                self._cerrar_turno_jarvis()

            if msg.server_content and msg.server_content.input_transcription and msg.server_content.input_transcription.text:
                if self._buf_jarvis:
                    # Llegó una transcripción nueva del usuario mientras
                    # todavía había una respuesta de Jarvis sin cerrar
                    # (turn_complete no llegó a tiempo) — cerrarla antes de
                    # empezar a acumular la del usuario, así no se mezclan.
                    self._cerrar_turno_jarvis()
                self._buf_usuario += msg.server_content.input_transcription.text
                self._esperando_respuesta = True

            if msg.server_content and msg.server_content.output_transcription and msg.server_content.output_transcription.text:
                if self._buf_usuario:
                    self._cerrar_turno_usuario()
                self._buf_jarvis += msg.server_content.output_transcription.text

            if msg.data:
                if not self.hablando:
                    print(f"[VoiceEngine][{ts}] empezó a llegar audio de respuesta")
                if self._cola_salida is not None:
                    self._cola_salida.put(msg.data)

            if msg.tool_call:
                bloqueantes = []
                for fc in msg.tool_call.function_calls:
                    print(f"[VoiceEngine][{ts}] tool_call: {fc.name}({dict(fc.args or {})})")
                    if fc.name in _TOOLS_NO_BLOQUEANTES:
                        self._lanzar_tool_no_bloqueante(session, loop, fc)
                    else:
                        bloqueantes.append(fc)

                if bloqueantes:
                    t0 = time.monotonic()
                    respuestas = []
                    for fc in bloqueantes:
                        resultado = await loop.run_in_executor(
                            None, self.agente.ejecutar_tool_directa, fc.name, dict(fc.args or {}),
                        )
                        respuestas.append(types.FunctionResponse(
                            id=fc.id, name=fc.name, response={"result": resultado},
                        ))
                    print(f"[VoiceEngine][{time.strftime('%H:%M:%S')}] tool_call resuelto en {time.monotonic()-t0:.2f}s")
                    await session.send_tool_response(function_responses=respuestas)

    def _lanzar_tool_no_bloqueante(self, session, loop: asyncio.AbstractEventLoop, fc) -> None:
        """Dispara una tool NON_BLOCKING sin esperarla en línea — la task
        arma y manda su propia FunctionResponse al terminar, de forma
        independiente del resto de `_recibir_turno`."""
        task = asyncio.create_task(self._resolver_tool_no_bloqueante(session, loop, fc))
        self._tools_pendientes.append(task)
        task.add_done_callback(self._al_terminar_tool_no_bloqueante)

    def _al_terminar_tool_no_bloqueante(self, task: asyncio.Task) -> None:
        if task in self._tools_pendientes:
            self._tools_pendientes.remove(task)
        if not task.cancelled() and task.exception():
            print(f"[VoiceEngine][{time.strftime('%H:%M:%S')}] tool NON_BLOCKING falló: {task.exception()!r}")

    async def _resolver_tool_no_bloqueante(self, session, loop: asyncio.AbstractEventLoop, fc) -> None:
        t0 = time.monotonic()
        # Si `ejecutar_tool_directa` tira (no debería — cada tool atrapa sus
        # propias excepciones — pero si algún día una se escapa), igual hay
        # que mandar una FunctionResponse: sin ella el modelo queda esperando
        # una respuesta que nunca llega y el turno de audio se cuelga entero
        # (mismo síntoma que "se quedó escuchando, nunca respondió").
        try:
            resultado = await loop.run_in_executor(
                None, self.agente.ejecutar_tool_directa, fc.name, dict(fc.args or {}),
            )
        except Exception as e:
            resultado = f"Error ejecutando '{fc.name}': {e}"
        respuesta = types.FunctionResponse(
            id=fc.id, name=fc.name, response={"result": resultado},
            scheduling=_TOOLS_NO_BLOQUEANTES[fc.name],
        )
        print(f"[VoiceEngine][{time.strftime('%H:%M:%S')}] tool_call NON_BLOCKING '{fc.name}' "
              f"resuelto en {time.monotonic()-t0:.2f}s")
        await session.send_tool_response(function_responses=[respuesta])

    def _vaciar_cola_salida(self) -> None:
        cola = self._cola_salida
        if cola is None:
            return
        try:
            while True:
                cola.get_nowait()
        except queue.Empty:
            pass


def _check() -> None:
    """Self-check automático (sin red, sin mic real) del gate de eco de la
    Fase 11: `_rms_pcm16` y `_en_ventana_de_eco` son funciones puras. El
    barge-in de punta a punta con la Live API real queda para
    `_check_voz.py` (requiere un humano hablando)."""
    silencio = b"\x00\x00" * 800
    fuerte = struct.pack("<800h", *([20000, -20000] * 400))
    assert _rms_pcm16(b"") == 0.0, "chunk vacío debería dar RMS 0"
    assert _rms_pcm16(silencio) < 10, "RMS de silencio debería ser ~0"
    assert _rms_pcm16(fuerte) > _UMBRAL_RMS_ECO_DEFAULT, "RMS de audio fuerte debería superar el umbral"

    cola_vacia = queue.Queue()
    cola_con_datos = queue.Queue()
    cola_con_datos.put(b"x")
    ahora = 100.0
    assert _en_ventana_de_eco(cola_con_datos, 0.0, 0.6, ahora) is True, "cola con audio pendiente = ventana activa"
    assert _en_ventana_de_eco(cola_vacia, ahora - 0.1, 0.6, ahora) is True, "recién terminó de sonar = ventana activa"
    assert _en_ventana_de_eco(cola_vacia, ahora - 5.0, 0.6, ahora) is False, "hace rato que no suena = sin ventana"

    print("OK")


if __name__ == "__main__":
    _check()
