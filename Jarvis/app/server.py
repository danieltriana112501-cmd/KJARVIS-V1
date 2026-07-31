"""server.py — Flask local (SIEMPRE 127.0.0.1) que expone tareas,
recordatorios, configuración, chat de texto y el motor de voz a la interfaz
pywebview de la Fase 08. No reimplementa lógica: delega en los módulos ya
construidos en fases anteriores (tareas.py, recordatorios.py, config.py,
gemini_agent.py, voice_engine.py).
"""
from __future__ import annotations

import math
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from app import config
from app.actions.tareas import tareas as _tareas_tool, listar_tareas
from app.actions.recordatorios import (
    recordatorios as _recordatorios_tool,
    listar_todo as _listar_recordatorios,
    start_runner as _start_runner,
)
from app.gemini_agent import GeminiAgent
from app.tts_local import hablar
from app.voice_engine import (
    VoiceEngine,
    _rms_pcm16,
    _UMBRAL_RMS_ECO_DEFAULT,
    _SAMPLE_RATE_IN,
    _SAMPLE_RATE_OUT,
    _CHUNK_MS,
)

PUERTO = 5577

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

app = Flask(__name__, static_folder=None)

_lock = threading.Lock()
_agente_cache = {"api_key": None, "agente": None}
# ponytail: el motor de voz se recrea solo si cambian key/voz y no hay sesión
# activa; si el usuario cambia la key/voz DURANTE una sesión activa, esa
# sesión sigue con los valores viejos hasta que se detiene y se reinicia.
_voz_cache = {"api_key": None, "voice": None, "motor": None}
# Fase 09: flag simple para que /api/estado reporte "procesando" mientras
# /api/mensaje espera a GeminiAgent. Un solo usuario local, no hace falta lock.
_estado_texto = {"procesando": False}
# Fase 10: referencia a la ventana mini (PIP), inyectada por ui.py después de
# crearla — server.py no depende de pywebview para nada más que esto.
_pip = {"window": None}
# Fase 13: estado del test de micrófono (nivel en vivo, sin sesión de voz).
# Lock propio porque el callback de PortAudio corre en su propio hilo nativo,
# aparte de los hilos de Flask que atienden iniciar/detener/nivel.
_mic_test = {"activo": False, "nivel": 0.0, "stream": None}
_mic_test_lock = threading.Lock()
# Visto en vivo dos veces: abrir/cerrar un stream de prueba (mic-test o
# speaker-test) justo antes de arrancar una sesión de voz real deja esa
# sesión completamente muda (mic_activo sigue logueando, pero cero
# transcripción, nunca) — el dispositivo de audio en Windows queda en mal
# estado un momento después de que otro proceso/stream lo tocó. Cooldown
# real antes de abrir la sesión real si un test corrió hace poco.
_ultimo_test_audio = {"ts": 0.0}
_COOLDOWN_TEST_AUDIO_S = 2.0

# Escala lineal (RMS/300) probada contra hardware real (Fase 13): con voz
# normal-a-fuerte el RMS crudo de PCM16 se queda en cientos/pocos miles, muy
# lejos del techo de ~32767 — la barra casi no se movía salvo gritando. Un
# medidor de nivel de audio real es logarítmico (dBFS), no lineal: el oído y
# el rango dinámico de una señal de voz funcionan así. Piso en -60dBFS
# (silencio/ruido de fondo) a 0dBFS (full scale/clipping).
_DBFS_PISO = -60.0
_PCM16_FULL_SCALE = 32768.0


def _normalizar_nivel(rms: float) -> float:
    if rms <= 0:
        return 0.0
    dbfs = 20.0 * math.log10(min(rms, _PCM16_FULL_SCALE) / _PCM16_FULL_SCALE)
    return max(0.0, min(100.0, (dbfs - _DBFS_PISO) / -_DBFS_PISO * 100.0))


def set_pip_window(window) -> None:
    _pip["window"] = window


def _get_agente() -> GeminiAgent | None:
    api_key = config.get("gemini_api_key", "")
    if not api_key:
        return None
    with _lock:
        if _agente_cache["agente"] is None or _agente_cache["api_key"] != api_key:
            _agente_cache["agente"] = GeminiAgent(api_key=api_key)
            _agente_cache["api_key"] = api_key
        return _agente_cache["agente"]


def _get_motor_voz() -> VoiceEngine | None:
    agente = _get_agente()
    if agente is None:
        return None
    api_key = config.get("gemini_api_key", "")
    voice = config.get("voice", "Puck")
    with _lock:
        motor = _voz_cache["motor"]
        if motor is not None and motor.activo:
            return motor
        if motor is None or _voz_cache["api_key"] != api_key or _voz_cache["voice"] != voice:
            _voz_cache["motor"] = VoiceEngine(api_key=api_key, voice=voice, agente=agente)
            _voz_cache["api_key"] = api_key
            _voz_cache["voice"] = voice
        return _voz_cache["motor"]


@app.get("/")
def index():
    return send_from_directory(ASSETS_DIR, "index.html")


@app.get("/<path:filename>")
def assets(filename):
    return send_from_directory(ASSETS_DIR, filename)


@app.get("/api/tareas")
def get_tareas():
    return jsonify(listar_tareas())


@app.post("/api/tareas")
def post_tareas():
    parametros = request.get_json(force=True, silent=True) or {}
    mensaje = _tareas_tool(parametros)
    return jsonify({"message": mensaje, "tareas": listar_tareas()})


@app.get("/api/recordatorios")
def get_recordatorios():
    return jsonify(_listar_recordatorios())


@app.post("/api/recordatorios")
def post_recordatorios():
    parametros = request.get_json(force=True, silent=True) or {}
    mensaje = _recordatorios_tool(parametros)
    return jsonify({"message": mensaje, "recordatorios": _listar_recordatorios()})


@app.get("/api/config")
def get_config():
    settings = config.load_settings()
    settings["voces_disponibles"] = config.VOCES_DISPONIBLES
    return jsonify(settings)


@app.post("/api/config")
def post_config():
    datos = request.get_json(force=True, silent=True) or {}
    config.save_settings(datos)
    return jsonify(config.load_settings())


@app.post("/api/mensaje")
def post_mensaje():
    datos = request.get_json(force=True, silent=True) or {}
    texto = str(datos.get("texto", "")).strip()
    agente = _get_agente()
    if agente is None:
        return jsonify({"respuesta": "Falta configurar la API key de Gemini, señor."})
    _estado_texto["procesando"] = True
    try:
        respuesta = agente.procesar(texto)
    finally:
        _estado_texto["procesando"] = False
    return jsonify({"respuesta": respuesta})


@app.post("/api/voz/iniciar")
def post_voz_iniciar():
    motor = _get_motor_voz()
    if motor is None:
        return jsonify({"activo": False, "error": "Falta configurar la API key de Gemini, señor."})
    # Cooldown real (visto en vivo dos veces): si un test de mic/salida
    # tocó el dispositivo hace poco, esperar antes de abrir la sesión real
    # — abrirlo demasiado rápido después deja la sesión completamente muda
    # (nunca llega una transcripción, sin ningún error visible).
    espera = _COOLDOWN_TEST_AUDIO_S - (time.monotonic() - _ultimo_test_audio["ts"])
    if espera > 0:
        time.sleep(espera)
    motor.iniciar_sesion()
    return jsonify({"activo": True})


@app.post("/api/voz/detener")
def post_voz_detener():
    motor = _voz_cache["motor"]
    if motor is not None:
        motor.detener_sesion()
    return jsonify({"activo": False})


@app.get("/api/voz/estado")
def get_voz_estado():
    motor = _voz_cache["motor"]
    if motor is None:
        return jsonify({"activo": False, "error": None})
    return jsonify({"activo": motor.activo, "error": motor.ultimo_error})


@app.get("/api/audio-devices")
def get_audio_devices():
    """Dispositivos reales de PortAudio (los que usa `VoiceEngine`).

    La UI llenaba estos selectores con `navigator.mediaDevices.enumerateDevices()`,
    cuyos índices NO coinciden con los de PortAudio: guardar el "altavoz 3"
    del navegador terminaba mandando el audio al Asignador de sonido de
    Windows, que no suena — Jarvis respondía pero no se escuchaba nada.
    """
    import sounddevice as sd
    try:
        dispositivos = sd.query_devices()
        por_defecto = sd.default.device
    except Exception as e:
        return jsonify({"entrada": [], "salida": [], "error": str(e)})
    entrada, salida = [], []
    for i, d in enumerate(dispositivos):
        item = {"index": i, "nombre": d["name"]}
        if d["max_input_channels"] > 0:
            entrada.append(item)
        if d["max_output_channels"] > 0:
            salida.append(item)
    return jsonify({
        "entrada": entrada,
        "salida": salida,
        "default_entrada": por_defecto[0],
        "default_salida": por_defecto[1],
    })


@app.post("/api/mic-test/iniciar")
def post_mic_test_iniciar():
    """Abre un stream de entrada aparte solo para medir nivel — rechaza
    arrancar si hay una sesión de voz activa (dos streams compitiendo por el
    mismo dispositivo pueden fallar al abrir el segundo, o robarle el audio
    al primero en Windows)."""
    motor = _voz_cache["motor"]
    if motor is not None and motor.activo:
        return jsonify({
            "activo": False,
            "error": "Detené la sesión de voz antes de probar el micrófono, señor.",
        })

    datos = request.get_json(force=True, silent=True) or {}
    mic_idx = datos.get("mic_device_index")
    mic_idx = int(mic_idx) if mic_idx is not None else config.get("mic_device_index", -1)

    import sounddevice as sd
    with _mic_test_lock:
        if _mic_test["activo"]:
            return jsonify({"activo": True})

        def _callback(indata, frames, time_info, status):
            _mic_test["nivel"] = _normalizar_nivel(_rms_pcm16(bytes(indata)))

        try:
            stream = sd.RawInputStream(
                samplerate=_SAMPLE_RATE_IN, channels=1, dtype="int16",
                blocksize=int(_SAMPLE_RATE_IN * _CHUNK_MS / 1000),
                device=None if mic_idx == -1 else mic_idx,
                callback=_callback,
            )
            stream.start()
        except Exception as e:
            return jsonify({"activo": False, "error": f"No se pudo abrir el micrófono: {e}"})
        _mic_test["stream"] = stream
        _mic_test["nivel"] = 0.0
        _mic_test["activo"] = True
        _ultimo_test_audio["ts"] = time.monotonic()
    return jsonify({"activo": True})


@app.post("/api/mic-test/detener")
def post_mic_test_detener():
    with _mic_test_lock:
        stream = _mic_test["stream"]
        _mic_test["activo"] = False
        _mic_test["stream"] = None
        _mic_test["nivel"] = 0.0
    if stream is not None:
        try:
            stream.stop()
            stream.close()
        except Exception:
            pass
    _ultimo_test_audio["ts"] = time.monotonic()
    return jsonify({"activo": False})


@app.get("/api/mic-test/nivel")
def get_mic_test_nivel():
    return jsonify({
        "activo": _mic_test["activo"],
        "nivel": _mic_test["nivel"],
        # Mismo umbral (ajustable en datos/settings.json vía /api/config)
        # que usa el gate de eco/barge-in de VoiceEngine — este panel sirve
        # justamente para calibrarlo a ojo.
        "umbral": _normalizar_nivel(config.get("umbral_rms_eco", _UMBRAL_RMS_ECO_DEFAULT)),
    })


_TONO_HZ = 660.0
_TONO_DURACION_S = 0.7


def _generar_tono() -> bytes:
    import struct
    n = int(_SAMPLE_RATE_OUT * _TONO_DURACION_S)
    # Fade in/out corto (10ms) para no golpear el parlante con un click
    # seco al arrancar/parar el tono.
    fade_n = int(_SAMPLE_RATE_OUT * 0.01)
    muestras = []
    for i in range(n):
        amp = 0.5
        if i < fade_n:
            amp *= i / fade_n
        elif i > n - fade_n:
            amp *= (n - i) / fade_n
        valor = amp * math.sin(2 * math.pi * _TONO_HZ * i / _SAMPLE_RATE_OUT)
        muestras.append(int(valor * 32767))
    return struct.pack(f"<{n}h", *muestras)


@app.post("/api/speaker-test")
def post_speaker_test():
    """Reproduce un tono corto y audible en el dispositivo indicado —
    complemento del mic-test (Fase 13) para el otro lado: `stream.write()`
    puede no tirar error y aun así no sonar nada (visto en vivo con un
    dispositivo virtual), la única forma real de confirmarlo es escucharlo."""
    motor = _voz_cache["motor"]
    if motor is not None and motor.activo:
        return jsonify({
            "ok": False,
            "error": "Detené la sesión de voz antes de probar la salida, señor.",
        })

    datos = request.get_json(force=True, silent=True) or {}
    speaker_idx = datos.get("speaker_device_index")
    speaker_idx = int(speaker_idx) if speaker_idx is not None else config.get("speaker_device_index", -1)

    import sounddevice as sd
    try:
        stream = sd.RawOutputStream(
            samplerate=_SAMPLE_RATE_OUT, channels=1, dtype="int16",
            device=None if speaker_idx == -1 else speaker_idx,
        )
        stream.start()
        stream.write(_generar_tono())
        stream.stop()
        stream.close()
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})
    _ultimo_test_audio["ts"] = time.monotonic()
    return jsonify({"ok": True})


@app.get("/api/voz/transcripcion")
def get_voz_transcripcion():
    """Lo que se dijo/respondió en la sesión de voz activa (Fase 06 no
    exponía texto, solo audio — el usuario probando la app real no veía
    nada en pantalla de lo que dijo ni de lo que Jarvis contestó)."""
    motor = _voz_cache["motor"]
    if motor is None:
        return jsonify({"items": []})
    return jsonify({"items": motor.transcripciones})


@app.get("/api/estado")
def get_estado():
    """Estado agregado del asistente para el panel ASCII (Fase 09):
    inactivo/escuchando/hablando/procesando. Polling simple desde app.js."""
    if _estado_texto["procesando"]:
        estado = "procesando"
    else:
        motor = _voz_cache["motor"]
        if motor is not None and motor.activo:
            if motor.hablando:
                estado = "hablando"
            elif motor.procesando:
                estado = "procesando"
            else:
                estado = "escuchando"
        else:
            estado = "inactivo"
    return jsonify({"estado": estado})


@app.get("/api/pip/estado")
def get_pip_estado():
    return jsonify({"habilitado": bool(config.get("pip_habilitado", False))})


@app.post("/api/pip/toggle")
def post_pip_toggle():
    nuevo = not config.get("pip_habilitado", False)
    config.set("pip_habilitado", nuevo)
    ventana = _pip["window"]
    if ventana is not None:
        ventana.show() if nuevo else ventana.hide()
    return jsonify({"habilitado": nuevo})


# ponytail: agente fijado una sola vez al levantar el server; si el usuario
# recién configura la API key después de arrancar, las alarmas con
# action_prompt no la ven hasta reiniciar la app. Subir a resolución lazy
# (ej. un wrapper con .procesar que llame _get_agente() en cada disparo) si
# esto se vuelve un problema real de uso diario.
_start_runner(hablar, agente=_get_agente())
