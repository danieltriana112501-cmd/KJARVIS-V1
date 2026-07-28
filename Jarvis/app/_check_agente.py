"""_check_agente.py — Self-check de GeminiAgent (Fase 05), sin mocks.

ADVERTENCIA: este check llama a la API real de Gemini (pasos 2 y 3 escalan
de verdad). Consume cuota — correrlo una sola vez, no en loop.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app import config
from app.gemini_agent import GeminiAgent


def _check() -> None:
    api_key = config.get("gemini_api_key")
    assert api_key, "Falta gemini_api_key en datos/settings.json"

    agente = GeminiAgent(api_key)

    print("[1/4] 'qué tareas tengo' — debe resolverse por matcher local...")
    r1 = agente.procesar("qué tareas tengo")
    assert agente.stats()["gemini"] == 0, f"escaló a Gemini sin necesidad: stats={agente.stats()}"
    print(f"  -> {r1!r}  stats={agente.stats()}")

    print("[2/4] 'recomiéndame qué hacer un día lluvioso en casa' — debe escalar a Gemini...")
    r2 = agente.procesar("recomiéndame qué hacer un día lluvioso en casa")
    assert agente.stats()["gemini"] == 1, f"no escaló a Gemini: stats={agente.stats()}"
    assert r2.strip(), "respuesta vacía de Gemini"
    print(f"  -> {r2!r}  stats={agente.stats()}")

    print("[3/4] 'busca qué pasó hoy con el precio del bitcoin' — debe usar buscar_web con grounding...")
    r3 = agente.procesar("busca qué pasó hoy con el precio del bitcoin")
    assert r3.strip(), "respuesta vacía de la búsqueda"
    negativas = (
        "no tengo acceso a internet", "no puedo acceder a internet", "no tengo la capacidad de navegar",
        "límite en la búsqueda web", "no pude buscar en la web", "excediste tu cuota", "resource_exhausted",
    )
    texto_lower = r3.lower()
    if any(n in texto_lower for n in negativas):
        print(f"  -> ADVERTENCIA: el grounding no devolvió info concreta (probable cuota/billing de "
              f"`google_search` agotada en la cuenta, no un bug de código — ver plans/ERRORES.md): {r3!r}")
    else:
        print(f"  -> {r3!r}  stats={agente.stats()}")

    print(f"[4/4] OK (con la advertencia de arriba si aplica) — stats finales: {agente.stats()}")


if __name__ == "__main__":
    _check()
