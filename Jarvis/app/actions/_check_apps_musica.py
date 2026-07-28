"""_check_apps_musica.py — Self-check de open_app.py, musica.py y matcher.py,
sin mocks (Fase 04).

Los pasos 1 y 2 abren ventanas/navegador reales; requieren confirmación
visual humana (no automatizable sin ver pantalla) — se imprimen igual para
que quien corra el script pueda verificarlo a ojo.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.actions.open_app import open_app, _try_start_command
from app.actions.musica import buscar_youtube
from app.matcher import match_local


def _check() -> None:
    print("[0/5] Verificando que open_app rechaza metacaracteres de shell (Fase 05, endurecimiento).")
    marker = Path(__file__).resolve().parent / "marker_injection_test.txt"
    marker.unlink(missing_ok=True)
    inyeccion = open_app({"app_name": "nonexistent_xyz & echo INJECTED> marker_injection_test.txt"})
    assert not marker.exists(), "INYECCION: el metacaracter '&' llegó a shell=True sin filtrar"
    marker.unlink(missing_ok=True)
    assert _try_start_command("algo & echo hola") is False, "_try_start_command no rechazó '&'"
    assert _try_start_command("algo | echo hola") is False, "_try_start_command no rechazó '|'"
    print(f"  -> rechazado correctamente: {inyeccion}")

    print("[1/5] Abriendo bloc de notas — confirmar visualmente que se abrió Notepad.")
    resultado_app = open_app({"app_name": "bloc de notas"})
    print(f"  -> {resultado_app}")

    print("[2/5] Buscando 'lofi hip hop radio' en YouTube...")
    resultado_yt = buscar_youtube("lofi hip hop radio")
    assert resultado_yt is not None, "buscar_youtube no devolvió resultado"
    assert resultado_yt.get("title"), "título vacío"
    assert resultado_yt.get("url"), "url vacía"
    print(f"  -> title={resultado_yt['title']!r} url={resultado_yt['url']!r}")

    print("[3/5] Verificando matcher para 'abre calculadora'...")
    match_open = match_local("abre calculadora")
    assert match_open == {"tool": "open_app", "parameters": {"app_name": "calculadora"}}, \
        f"matcher open_app falló: {match_open}"

    print("[4/5] Verificando matcher para 'pon bohemian rhapsody'...")
    match_musica = match_local("pon bohemian rhapsody")
    assert match_musica == {
        "tool": "musica",
        "parameters": {"action": "play", "query": "bohemian rhapsody"},
    }, f"matcher musica falló: {match_musica}"

    print("[5/5] OK — pasos 1 y 2 requieren confirmación humana (ventana/navegador reales).")


if __name__ == "__main__":
    _check()
