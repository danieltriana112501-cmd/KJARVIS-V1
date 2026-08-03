"""ui.py — Ventana pywebview de Jarvis (Fase 08) + calavera flotante (Fase 19).

Levanta el Flask de `server.py` en un thread aparte, abre la ventana
principal, y lanza `overlay.py` (Fase 19) como PROCESO APARTE.

La ventana mini pywebview de la Fase 10 se elimina acá: `transparent=True`
no está soportado por el backend de pywebview en Windows (queda como un
rectángulo negro sólido, ver
plans/INVESTIGACION-2026-07-27-voz-tools-ui.md sección 10.2) — no es un bug
de este proyecto, es una limitación del motor. El overlay tkinter la
reemplaza con transparencia real por color-key (sección 10.3-10.5 de esa
misma investigación, verificado con los assets reales en
plans/INVESTIGACION-2026-08-01-overlay-situaciones.md).

Correr Tk y pywebview en el mismo proceso/hilo principal no es viable (los
dos quieren el hilo principal) — de ahí el subprocess en vez de un thread.
"""
from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path

import webview

from app.server import PUERTO, app as _flask_app

_JARVIS_DIR = Path(__file__).resolve().parent.parent


def _levantar_flask() -> None:
    _flask_app.run(host="127.0.0.1", port=PUERTO, threaded=True, use_reloader=False, debug=False)


def _lanzar_overlay() -> subprocess.Popen:
    # CREATE_NO_WINDOW: sin esto, el hijo (subsistema consola) abre su propia
    # ventana cmd nueva porque no hereda consola del padre -- se ve como un
    # segundo cmd fantasma junto a la ventana principal.
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    return subprocess.Popen(
        [sys.executable, "-m", "app.overlay"],
        cwd=str(_JARVIS_DIR),
        creationflags=creationflags,
    )


def main() -> None:
    threading.Thread(target=_levantar_flask, daemon=True).start()
    webview.create_window(
        "JARVIS",
        f"http://127.0.0.1:{PUERTO}/",
        width=1000,
        height=700,
        min_size=(760, 540),
        resizable=True,
        background_color="#050505",
    )
    overlay_proc = _lanzar_overlay()
    try:
        webview.start()
    finally:
        overlay_proc.terminate()


if __name__ == "__main__":
    main()
