"""diagnostico_mic.py — Prueba de captura de mic aislada de Flask/threads/UI.

Uso:
    python tools/diagnostico_mic.py            # lista dispositivos de entrada
    python tools/diagnostico_mic.py <indice>   # captura en vivo 10s con ESE indice,
                                                # mismos parametros que voice_engine.py
                                                # (16kHz mono, chunks de 30ms)

Corre desde la carpeta Jarvis/. Hablale al mic mientras corre y mira si el
numero sube. Sirve para encontrar, de los varios indices que aparecen para
"lo mismo", cual responde de verdad — sin depender del server ni del panel.
"""
import sys
import time

import sounddevice as sd

sys.path.insert(0, ".")
from app.voice_engine import _rms_pcm16, _SAMPLE_RATE_IN, _CHUNK_MS  # noqa: E402


def listar():
    print(f"default input index: {sd.default.device[0]}\n")
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            hostapi = sd.query_hostapis(d["hostapi"])["name"]
            print(f"{i:3d}  {d['name']!r:45s} hostapi={hostapi:20s} sr_nativo={d['default_samplerate']:.0f}")


def probar(indice: int, segundos: float = 10.0):
    print(f"Capturando indice {indice} durante {segundos:.0f}s a {_SAMPLE_RATE_IN}Hz mono. Hablá fuerte cerca del mic.\n")
    fin = time.monotonic() + segundos

    def callback(indata, frames, time_info, status):
        if status:
            print(f"  [status] {status}")
        rms = _rms_pcm16(bytes(indata))
        barra = "#" * min(60, int(rms / 100))
        print(f"\rRMS={rms:7.1f} {barra:<60s}", end="", flush=True)

    try:
        with sd.RawInputStream(
            samplerate=_SAMPLE_RATE_IN, channels=1, dtype="int16",
            blocksize=int(_SAMPLE_RATE_IN * _CHUNK_MS / 1000),
            device=indice, callback=callback,
        ):
            while time.monotonic() < fin:
                time.sleep(0.05)
    except Exception as e:
        print(f"\nERROR abriendo/capturando indice {indice}: {e!r}")
        return
    print("\n\nListo.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        listar()
    else:
        probar(int(sys.argv[1]))
