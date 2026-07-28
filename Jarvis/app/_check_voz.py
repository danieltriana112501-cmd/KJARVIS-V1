"""_check_voz.py — Self-check MANUAL de `VoiceEngine` (Fase 06).

Este check requiere un humano hablando de verdad al micrófono — no es
automatizable, y consume cuota REAL de la Live API (más limitada que la de
texto). No correrlo repetidamente sin necesidad; una vez por verificación
alcanza.

Uso:
    python app/_check_voz.py
"""
from app import config
from app.gemini_agent import GeminiAgent
from app.voice_engine import VoiceEngine


def main() -> None:
    api_key = config.get("gemini_api_key")
    if not api_key:
        print("Falta gemini_api_key en datos/settings.json.")
        return

    voice = config.get("voice")
    agente = GeminiAgent(api_key=api_key)
    motor = VoiceEngine(api_key=api_key, voice=voice, agente=agente)

    print(f"Modelo Live: {motor.MODEL}")
    print(f"Voz configurada: {voice}")
    print("Iniciando sesión...")
    motor.iniciar_sesion()

    print()
    print("Sesión iniciada. Decí algo como 'qué hora es' o")
    print("'agrégame una tarea para mañana'.")
    print("Confirmá de oído que la respuesta suena con la voz elegida arriba.")
    print("Si pediste una tarea/recordatorio, confirmá después que quedó")
    print("guardada revisando Jarvis/datos/tareas.json o recordatorios.json.")
    print()
    input("Presioná ENTER para cortar la sesión... ")

    motor.detener_sesion()
    print(f"Sesión detenida. activo={motor.activo}")
    if motor.ultimo_error:
        print(f"Último error registrado: {motor.ultimo_error}")


if __name__ == "__main__":
    main()
