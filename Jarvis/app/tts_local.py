"""tts_local.py — Síntesis de voz local con pyttsx3, sin pasar por Gemini.

Reutilizable por cualquier fase que necesite avisar algo por voz sin gastar
cuota de API (ej. el runner de recordatorios de la Fase 03).
"""
import threading

_lock = threading.Lock()


def hablar(texto: str) -> None:
    """Lee `texto` en voz alta con el motor TTS del sistema (bloqueante)."""
    if not texto:
        return
    # pyttsx3 no es thread-safe (usa SAPI5 vía COM); crear un motor nuevo por
    # llamada evita corromper el estado si dos avisos se disparan seguidos.
    with _lock:
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.say(texto)
            engine.runAndWait()
            engine.stop()
        except Exception as e:
            print(f"[TTS] Error: {e}")


def _check() -> None:
    hablar("")  # no-op: confirma que un texto vacío no rompe nada
    hablar("Prueba de voz de Jarvis.")  # ejercita pyttsx3 de verdad
    print("OK")


if __name__ == "__main__":
    _check()
