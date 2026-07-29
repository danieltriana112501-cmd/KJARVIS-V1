"""navegador.py — Abrir URLs con un perfil de Chrome fijo (Fase 17).

Con varias cuentas de Google logueadas, Chrome puede quedarse esperando que
el usuario elija perfil (`picker_shown`) — Jarvis no puede resolver eso, y
el pedido "parece que no abrió" (ver plans/INVESTIGACION..., sección 4.1).
`--profile-directory` salta el selector; sin perfil configurado, cae al
comportamiento anterior (`webbrowser.open`).
"""
from __future__ import annotations

import subprocess
import webbrowser
import winreg
from urllib.parse import urlparse

from app import config

_ESQUEMAS_PERMITIDOS = {"http", "https"}


def _chrome_exe() -> str | None:
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
        ) as k:
            return winreg.QueryValue(k, None)
    except OSError:
        return None


def abrir_url(url: str) -> bool:
    """Abre `url` en el navegador. Rechaza cualquier esquema que no sea
    http/https (la url puede venir de la salida de un modelo) y nunca usa
    `shell=True` — los argumentos van como lista."""
    esquema = urlparse(url).scheme.lower()
    if esquema not in _ESQUEMAS_PERMITIDOS:
        return False

    perfil = config.get("chrome_profile_dir", "")
    if perfil:
        exe = _chrome_exe()
        if exe:
            try:
                subprocess.Popen([exe, f"--profile-directory={perfil}", url])
                return True
            except OSError:
                pass

    return webbrowser.open(url)


def _check() -> None:
    assert abrir_url("javascript:alert(1)") is False, "esquema no-http debería rechazarse"
    assert abrir_url("file:///C:/Windows/win.ini") is False, "file:// debería rechazarse"
    exe = _chrome_exe()
    assert exe is None or exe.lower().endswith("chrome.exe"), "ruta de chrome.exe rara"
    print("OK")


if __name__ == "__main__":
    _check()
