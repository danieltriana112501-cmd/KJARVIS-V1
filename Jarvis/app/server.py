"""server.py — Flask local (SIEMPRE 127.0.0.1) que expone tareas,
recordatorios, configuración, chat de texto y el motor de voz a la interfaz
pywebview de la Fase 08. No reimplementa lógica: delega en los módulos ya
construidos en fases anteriores (tareas.py, recordatorios.py, config.py,
gemini_agent.py, voice_engine.py).
"""
from __future__ import annotations

import threading
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
from app.voice_engine import VoiceEngine

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
