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
import threading
import time

import sounddevice as sd
from google import genai
from google.genai import types

from app import config
from app.gemini_agent import GeminiAgent

_SISTEMA = (
    "Sos Jarvis, un asistente de voz personal. Respondé en español, de forma "
    "breve y directa, con trato cordial hacia quien te habla."
)

_SAMPLE_RATE_IN = 16000
_SAMPLE_RATE_OUT = 24000
_CHUNK_MS = 30


class VoiceEngine:
    MODEL = "gemini-2.5-flash-native-audio-latest"
    _UMBRAL_HABLANDO_S = 0.6

    def __init__(self, api_key: str, voice: str, agente: GeminiAgent):
        self._client = genai.Client(api_key=api_key)
        self.voice = voice
        self.agente = agente
        self._thread: threading.Thread | None = None
        self._detener_flag: threading.Event | None = None
        self._activo = False
        self.ultimo_error: str | None = None
        self._ultimo_audio_ts = 0.0
        self._esperando_respuesta = False
        self._buf_usuario = ""
        self._buf_jarvis = ""
        self.transcripciones: list[dict] = []  # [{"quien": "usuario"|"jarvis", "texto": ...}]
        self._cola_salida: queue.Queue | None = None

    @property
    def activo(self) -> bool:
        return self._activo

    @property
    def hablando(self) -> bool:
        """True mientras queda audio de Jarvis por reproducir (o terminó de
        sonar hace menos de _UMBRAL_HABLANDO_S) — usado por `/api/estado`
        (Fase 09) para distinguir "escuchando" de "hablando", y por
        `_enviar_audio` para silenciar el mic y evitar el eco."""
        if not self._activo:
            return False
        if self._cola_salida is not None and not self._cola_salida.empty():
            return True
        return (time.monotonic() - self._ultimo_audio_ts) < self._UMBRAL_HABLANDO_S

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
        self._esperando_respuesta = False
        self._buf_usuario = ""
        self._buf_jarvis = ""
        self.transcripciones = []
        self._activo = True
        self._thread = threading.Thread(target=self._correr_en_thread, daemon=True)
        self._thread.start()

    def detener_sesion(self) -> None:
        if not self._activo or not self._detener_flag:
            return
        self._detener_flag.set()
        if self._thread:
            self._thread.join(timeout=10)
        self._activo = False

    def _correr_en_thread(self) -> None:
        try:
            asyncio.run(self._sesion_async())
        except Exception as e:
            self.ultimo_error = str(e)
            print(f"[VoiceEngine] Error: {e}")
        finally:
            self._activo = False

    async def _sesion_async(self) -> None:
        live_config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            tools=[self.agente.tools],
            system_instruction=_SISTEMA,
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self.voice)
                )
            ),
            # Sin esto, la Live API no manda ningún texto — solo audio — y no
            # había forma de mostrar en pantalla lo que el usuario dijo ni lo
            # que Jarvis respondió (reportado probando la app real).
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            # NO agregar `realtime_input_config` acá: se probó configurar el
            # VAD explícitamente (start/end sensitivity, silence_duration_ms)
            # y el servidor dejó de mandar CUALQUIER mensaje — ni una sola
            # transcripción, con el mic enviando audio normalmente. Sin ese
            # campo, el VAD automático por defecto funciona. Ver
            # plans/ERRORES.md, entrada Fase 06 (VAD explícito).
        )

        mic_idx = config.get("mic_device_index", -1)
        speaker_idx = config.get("speaker_device_index", -1)

        async with self._client.aio.live.connect(model=self.MODEL, config=live_config) as session:
            print(f"[VoiceEngine][{time.strftime('%H:%M:%S')}] sesion conectada, modelo={self.MODEL}")
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
                args=(stream_out, self._cola_salida, fin_reproductor),
                daemon=True,
            )
            hilo_out.start()

            enviar_task = asyncio.create_task(self._enviar_audio(session, cola_in))
            recibir_task = asyncio.create_task(self._recibir(session, loop))
            try:
                while not self._detener_flag.is_set():
                    # Si alguna de las dos tareas murió (excepción propia o
                    # corte del servidor), no tiene sentido seguir: se corta
                    # la sesión y se reporta. Antes la excepción quedaba
                    # invisible dentro de la task y la app parecía "colgada".
                    for t, nombre in ((enviar_task, "enviar"), (recibir_task, "recibir")):
                        if t.done():
                            exc = t.exception()
                            msg = f"tarea '{nombre}' terminó" + (f": {exc!r}" if exc else " sin error")
                            print(f"[VoiceEngine][{time.strftime('%H:%M:%S')}] {msg}")
                            self.ultimo_error = msg
                            self._detener_flag.set()
                    await asyncio.sleep(0.2)
            finally:
                enviar_task.cancel()
                recibir_task.cancel()
                for t in (enviar_task, recibir_task):
                    try:
                        await t
                    except (asyncio.CancelledError, Exception):
                        pass
                fin_reproductor.set()
                self._cola_salida = None
                hilo_out.join(timeout=2)
                stream_in.stop()
                stream_in.close()
                stream_out.stop()
                stream_out.close()

    def _reproducir_loop(self, stream_out, cola: "queue.Queue", fin: threading.Event) -> None:
        while not fin.is_set():
            try:
                datos = cola.get(timeout=0.2)
            except queue.Empty:
                continue
            if datos is None:
                continue
            try:
                stream_out.write(datos)
                self._ultimo_audio_ts = time.monotonic()
            except Exception as e:
                print(f"[VoiceEngine][{time.strftime('%H:%M:%S')}] error reproduciendo audio: {e!r}")

    async def _enviar_audio(self, session, cola_in: "asyncio.Queue[bytes]") -> None:
        # DEBUG temporal: confirma que el mic realmente está mandando audio
        # (si esto no aparece cada ~1.5s, el problema es el dispositivo de
        # entrada, no la API). Quitar una vez diagnosticado el reporte del
        # usuario de "responde lento / no responde" en voz.
        n = 0
        while True:
            chunk = await cola_in.get()
            n += 1
            if n % 50 == 0:
                print(f"[VoiceEngine][{time.strftime('%H:%M:%S')}] mic activo, {n} chunks enviados")
            # ponytail: sin cancelación de eco real, el parlante+mic en el
            # mismo dispositivo hacen que Jarvis "se escuche a sí mismo" y el
            # servidor lo interpreta como el usuario interrumpiendo. Mientras
            # Jarvis habla, se manda SILENCIO (mismos bytes, en cero) en vez
            # de saltear el envío del todo — cortar el streaming por completo
            # (probado, ver plans/ERRORES.md) dejaba al detector de voz del
            # servidor en un estado roto: después de la primera respuesta,
            # ninguna transcripción nueva llegaba nunca más en esa sesión.
            # Mandar silencio mantiene el streaming continuo que la API
            # espera, sin el eco. Con auriculares no haría falta ninguno de
            # los dos; si se agrega selector de auriculares en config,
            # condicionar esto a "sin auriculares".
            if self.hablando:
                chunk = b"\x00" * len(chunk)
            await session.send_realtime_input(
                audio=types.Blob(data=chunk, mime_type=f"audio/pcm;rate={_SAMPLE_RATE_IN}")
            )

    async def _recibir(self, session, loop: asyncio.AbstractEventLoop) -> None:
        # `session.receive()` es un generador POR TURNO: se agota cuando el
        # modelo termina de responder. Sin este `while`, la tarea terminaba
        # después del primer intercambio y no se leía nada más en toda la
        # sesión — de ahí el síntoma "responde una vez y después se queda
        # escuchando para siempre". Hay que volver a pedirlo cada turno.
        while True:
            await self._recibir_turno(session, loop)

    async def _recibir_turno(self, session, loop: asyncio.AbstractEventLoop) -> None:
        async for msg in session.receive():
            ts = time.strftime('%H:%M:%S')

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
                for fc in msg.tool_call.function_calls:
                    print(f"[VoiceEngine][{ts}] tool_call: {fc.name}({dict(fc.args or {})})")
                t0 = time.monotonic()
                respuestas = []
                for fc in msg.tool_call.function_calls:
                    resultado = await loop.run_in_executor(
                        None, self.agente.ejecutar_tool_directa, fc.name, dict(fc.args or {}),
                    )
                    respuestas.append(types.FunctionResponse(
                        id=fc.id, name=fc.name, response={"result": resultado},
                    ))
                print(f"[VoiceEngine][{time.strftime('%H:%M:%S')}] tool_call resuelto en {time.monotonic()-t0:.2f}s")
                await session.send_tool_response(function_responses=respuestas)

    def _vaciar_cola_salida(self) -> None:
        cola = self._cola_salida
        if cola is None:
            return
        try:
            while True:
                cola.get_nowait()
        except queue.Empty:
            pass
