"""_check_tareas.py — Self-check de tareas.py y matcher.py, sin mocks (Fase 02)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.actions.tareas import tareas, TAREAS_PATH
from app.matcher import match_local


def _check() -> None:
    # Respaldar tareas.json real para no dejar residuo de la tarea de prueba.
    backup = TAREAS_PATH.read_text(encoding="utf-8") if TAREAS_PATH.exists() else None
    try:
        creada = tareas({"action": "add", "description": "probar sistema", "date": "mañana"})
        assert "probar sistema" in creada, f"no creó la tarea: {creada}"

        listado = tareas({"action": "list"})
        assert "probar sistema" in listado, f"no aparece en el listado: {listado}"

        completado = tareas({"action": "complete", "description": "probar sistema"})
        assert "completada" in completado, f"no se completó: {completado}"

        match_list = match_local("qué tareas tengo")
        assert match_list == {"tool": "tareas", "parameters": {"action": "list"}}, \
            f"matcher list falló: {match_list}"

        assert match_local("cuéntame un chiste") is None, "matcher confundió texto no relacionado"

        print("OK")
    finally:
        if backup is None:
            TAREAS_PATH.unlink(missing_ok=True)
        else:
            TAREAS_PATH.write_text(backup, encoding="utf-8")


if __name__ == "__main__":
    _check()
