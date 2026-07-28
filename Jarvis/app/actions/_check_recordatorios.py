"""_check_recordatorios.py — Self-check de recordatorios.py y matcher.py, sin mocks (Fase 03).

Crea un recordatorio real a 5 segundos, arranca el runner con un tts_fn de prueba
y espera a que dispare de verdad (usa la hora real del sistema, sin mockear time).
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.actions.recordatorios import crear_recordatorio, start_runner, REM_PATH, ALARM_PATH
from app.matcher import match_local

_avisos = []


def _tts_prueba(texto: str) -> None:
    print(f"[TTS] {texto}")
    _avisos.append(texto)


def _check() -> None:
    backup_rem = REM_PATH.read_text(encoding="utf-8") if REM_PATH.exists() else None
    backup_alarm = ALARM_PATH.read_text(encoding="utf-8") if ALARM_PATH.exists() else None
    try:
        item = crear_recordatorio("probar sistema", when="en 5 segundos")
        assert item is not None, "no se pudo crear el recordatorio de prueba"

        start_runner(_tts_prueba)
        start_runner(_tts_prueba)  # debe ser idempotente, no debe duplicar el hilo

        # El runner revisa cada 10s; el primer chequeo ocurre apenas arranca
        # (antes de que pasen los 5s), así que hace falta esperar al segundo.
        time.sleep(16)

        assert any("probar sistema" in t for t in _avisos), \
            f"el runner no disparó el aviso esperado, avisos recibidos: {_avisos}"

        match_list = match_local("qué recordatorios tengo")
        assert match_list == {"tool": "recordatorios", "parameters": {"action": "list"}}, \
            f"matcher list falló: {match_list}"

        print("OK")
    finally:
        if backup_rem is None:
            REM_PATH.unlink(missing_ok=True)
        else:
            REM_PATH.write_text(backup_rem, encoding="utf-8")
        if backup_alarm is None:
            ALARM_PATH.unlink(missing_ok=True)
        else:
            ALARM_PATH.write_text(backup_alarm, encoding="utf-8")


if __name__ == "__main__":
    _check()
