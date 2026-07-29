"""config.py — Configuración local del asistente (API key, voz, dispositivos).

Los valores se guardan en `Jarvis/datos/settings.json` como JSON plano
(uso personal, sin encriptación).
"""
import json
import threading
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATOS_DIR = BASE_DIR / "datos"
SETTINGS_PATH = DATOS_DIR / "settings.json"

_lock = threading.Lock()

DEFAULTS = {
    "gemini_api_key": "",
    "voice": "Puck",
    "mic_device_index": -1,
    "speaker_device_index": -1,
    "location": "",
    "morning_brief_time": "",
    "pip_habilitado": False,
    "usar_auriculares": False,
    # Filtro cavernoso (eco corto + apagado de agudos) sobre el audio de
    # salida de la Live API. La API no permite pitch-shift real (cambiaría
    # duración y desincronizaría la cola de reproducción, ver audio_fx.py),
    # así que esto es lo más "de ultratumba" que se puede sumar sin tocar
    # el pipeline en tiempo real. Default apagado por si mete artefactos.
    "voz_ultratumba": False,
    # Carpeta de perfil de Chrome (NO el nombre visible, la carpeta real —
    # confirmar con chrome://version o Local State). Vacío = comportamiento
    # anterior (webbrowser.open, sujeto al selector de perfiles). Ver
    # app/actions/navegador.py y plans/INVESTIGACION..., sección 4.2.
    "chrome_profile_dir": "",
}

VOCES_DISPONIBLES = [
    "Aoede", "Charon", "Fenrir", "Kore",
    "Puck", "Orus", "Leda", "Zephyr",
]


def _read() -> dict:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write(data: dict) -> None:
    DATOS_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_settings() -> dict:
    with _lock:
        existentes = _read()
        merged = {**DEFAULTS, **existentes}
        if merged != existentes:
            _write(merged)
        return merged


def save_settings(data: dict) -> None:
    with _lock:
        actuales = {**DEFAULTS, **_read()}
        for key, value in data.items():
            if key == "voice" and value not in VOCES_DISPONIBLES:
                continue
            actuales[key] = value
        _write(actuales)


def get(key: str, default=None):
    return load_settings().get(key, default)


def set(key: str, value) -> None:
    save_settings({key: value})


def _check() -> None:
    settings = load_settings()
    assert all(k in settings for k in DEFAULTS), "faltan claves default"

    save_settings({"voice": "Kore"})
    assert get("voice") == "Kore", "no guardó voz válida"

    save_settings({"voice": "NoExiste"})
    assert get("voice") == "Kore", "aceptó una voz inválida"

    print("OK")


if __name__ == "__main__":
    _check()
