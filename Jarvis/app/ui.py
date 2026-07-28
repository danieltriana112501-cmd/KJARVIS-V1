"""ui.py — Ventana pywebview de Jarvis (Fase 08) + ventana mini PIP (Fase 10).

Levanta el Flask de `server.py` en un thread aparte y abre la ventana
principal más una segunda ventana flotante sin bordes (picture-in-picture)
que reutiliza la misma página en `?modo=mini`.
"""
from __future__ import annotations

import threading

import webview

from app import config
from app.server import PUERTO, app as _flask_app, set_pip_window

MINI_ANCHO = 200
MINI_ALTO = 200
MINI_MARGEN = 24


def _levantar_flask() -> None:
    _flask_app.run(host="127.0.0.1", port=PUERTO, threaded=True, use_reloader=False, debug=False)


def _crear_ventana_mini():
    pantalla = webview.screens[0]
    x = pantalla.width - MINI_ANCHO - MINI_MARGEN
    y = pantalla.height - MINI_ALTO - MINI_MARGEN
    return webview.create_window(
        "Jarvis Mini",
        f"http://127.0.0.1:{PUERTO}/?modo=mini",
        width=MINI_ANCHO,
        height=MINI_ALTO,
        x=x,
        y=y,
        frameless=True,
        easy_drag=True,
        on_top=True,
        transparent=True,
        resizable=False,
        hidden=not config.get("pip_habilitado", False),
        background_color="#050505",
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
    mini = _crear_ventana_mini()
    set_pip_window(mini)
    webview.start()


if __name__ == "__main__":
    main()
