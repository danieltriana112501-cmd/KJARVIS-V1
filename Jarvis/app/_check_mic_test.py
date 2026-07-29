"""_check_mic_test.py — Self-check automatizable de la Fase 13 (test de
micrófono: nivel en vivo, guard contra sesión de voz activa).

No requiere hardware de audio real ni red: `sounddevice.RawInputStream` se
reemplaza por un doble de prueba que invoca el callback a mano con bytes
PCM16 fabricados, y `start_runner` de `recordatorios.py` se neutraliza ANTES
de importar `app.server` — importar ese módulo dispara
`_start_runner(hablar, agente=_get_agente())` al final del archivo, que si
corriera de verdad podría leer/escribir `datos/recordatorios.json` reales y
hasta reproducir un aviso por TTS si algo estuviera vencido en ese momento
(ver plans/ERRORES.md, Fase 11, sobre no pisar/disparar datos reales al
correr un self-check).

El flujo end-to-end con un humano hablando de verdad frente al mic (puntos
5-7 de la Verificación de la fase) queda pendiente — ver plans/phase-13-test-microfono.md.

Uso:
    python app/_check_mic_test.py
"""
import struct
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import app.actions.recordatorios as recordatorios_mod
recordatorios_mod.start_runner = lambda *a, **k: None  # ver docstring

import app.server as server


class _StreamFalso:
    """Doble de `sd.RawInputStream`: no toca hardware, guarda el callback
    para que el test lo dispare a mano y registra start/stop/close."""

    instancias_abiertas = 0

    def __init__(self, samplerate, channels, dtype, blocksize, device, callback):
        self.callback = callback
        self.cerrado = False
        _StreamFalso.instancias_abiertas += 1

    def start(self):
        pass

    def stop(self):
        pass

    def close(self):
        self.cerrado = True
        _StreamFalso.instancias_abiertas -= 1


def _pcm16_silencio(n=800) -> bytes:
    return b"\x00\x00" * n


def _pcm16_fuerte(n=400) -> bytes:
    return struct.pack(f"<{n * 2}h", *([20000, -20000] * n))


def _pcm16_maximo(n=400) -> bytes:
    return struct.pack(f"<{n * 2}h", *([32767, -32767] * n))


def _check() -> None:
    print("[1/4] _normalizar_nivel: escala 0-100, satura en 100...")
    assert server._normalizar_nivel(0) == 0.0
    assert 0 < server._normalizar_nivel(150) < 100
    assert server._normalizar_nivel(999999) == 100.0
    print("  -> OK")

    print("[2/4] guard: rechaza iniciar con una sesión de voz activa, sin abrir stream...")
    motor_falso = SimpleNamespace(activo=True)
    server._voz_cache["motor"] = motor_falso
    with server.app.test_client() as c:
        resp = c.post("/api/mic-test/iniciar", json={"mic_device_index": -1})
        data = resp.get_json()
        assert resp.status_code == 200, resp.status_code
        assert data["activo"] is False, data
        assert "sesión de voz" in data["error"], data
        assert server._mic_test["activo"] is False
    server._voz_cache["motor"] = None
    print(f"  -> OK, rechazado: {data['error']!r}")

    print("[3/4] flujo completo iniciar -> nivel sube con audio fuerte -> detener libera el stream...")
    import sounddevice
    real_sd = sounddevice.RawInputStream
    sounddevice.RawInputStream = _StreamFalso
    try:
        with server.app.test_client() as c:
            resp = c.post("/api/mic-test/iniciar", json={"mic_device_index": -1})
            data = resp.get_json()
            assert data["activo"] is True, data
            assert _StreamFalso.instancias_abiertas == 1, "no abrió el stream de prueba"

            stream = server._mic_test["stream"]
            stream.callback(_pcm16_silencio(), 800, None, None)
            nivel_silencio = c.get("/api/mic-test/nivel").get_json()
            assert nivel_silencio["activo"] is True
            assert nivel_silencio["nivel"] < 5.0, nivel_silencio

            stream.callback(_pcm16_fuerte(), 400, None, None)
            nivel_fuerte = c.get("/api/mic-test/nivel").get_json()
            assert nivel_fuerte["nivel"] > nivel_silencio["nivel"], nivel_fuerte
            assert nivel_fuerte["nivel"] > nivel_fuerte["umbral"], "audio fuerte debería cruzar el umbral de 'te escucho'"
            assert 0 < nivel_fuerte["umbral"] < 100, nivel_fuerte

            stream.callback(_pcm16_maximo(), 400, None, None)
            nivel_maximo = c.get("/api/mic-test/nivel").get_json()
            # Escala logarítmica (dBFS, Fase 13 recalibrada contra hardware
            # real): int16 real nunca pega exactamente en el full-scale de
            # 32768 (el máximo representable es 32767), así que el resultado
            # queda pegadísimo a 100 pero no exacto — tolerancia chica en vez
            # de igualdad estricta.
            assert nivel_maximo["nivel"] > 99.9, "audio al tope de la escala 32767 debería saturar la barra cerca de 100"

            resp = c.post("/api/mic-test/detener")
            data = resp.get_json()
            assert data["activo"] is False, data
            assert stream.cerrado is True, "el stream no se cerró al detener"
            assert _StreamFalso.instancias_abiertas == 0, "quedó un stream huérfano"

            nivel_tras_detener = c.get("/api/mic-test/nivel").get_json()
            assert nivel_tras_detener["activo"] is False
            assert nivel_tras_detener["nivel"] == 0.0
        print(f"  -> OK, silencio={nivel_silencio['nivel']:.1f} fuerte={nivel_fuerte['nivel']:.1f} "
              f"umbral={nivel_fuerte['umbral']:.1f}")

        print("[4/4] tras detener, se puede iniciar de nuevo (dispositivo no queda 'busy')...")
        with server.app.test_client() as c:
            resp = c.post("/api/mic-test/iniciar", json={"mic_device_index": -1})
            data = resp.get_json()
            assert data["activo"] is True, data
            assert _StreamFalso.instancias_abiertas == 1
            c.post("/api/mic-test/detener")
            assert _StreamFalso.instancias_abiertas == 0
        print("  -> OK")
    finally:
        sounddevice.RawInputStream = real_sd

    print("OK")


if __name__ == "__main__":
    _check()
