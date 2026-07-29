"""open_app.py - Robust application launcher for Windows.

Strategy (in order):
1. Direct mapping (English + Spanish aliases) -> known executable / URI scheme.
2. os.startfile() with mapped target.
3. Lookup in HKCU/HKLM `App Paths` registry key.
4. Windows `start` command (resolves App Paths and Store URIs).
5. Recursive scan of Start Menu (.lnk shortcuts) by fuzzy match.
6. Last resort: try the raw name with `start`.
"""
from __future__ import annotations

import os
import re
import sys
import shutil
import subprocess
from pathlib import Path


# --------------------------- Aliases ---------------------------------
# Map user-spoken names to a real launch target (executable, URI, or shortcut name).
# Keys must be lowercase.
_ALIASES: dict = {
    # System
    "notepad": "notepad.exe",
    "bloc de notas": "notepad.exe",
    "calculator": "calc.exe",
    "calculadora": "calc.exe",
    "calc": "calc.exe",
    "paint": "mspaint.exe",
    "pinta": "mspaint.exe",
    "explorer": "explorer.exe",
    "explorador": "explorer.exe",
    "explorador de archivos": "explorer.exe",
    "file explorer": "explorer.exe",
    "cmd": "cmd.exe",
    "simbolo del sistema": "cmd.exe",
    "command prompt": "cmd.exe",
    "powershell": "powershell.exe",
    "terminal": "wt.exe",
    "windows terminal": "wt.exe",
    "task manager": "taskmgr.exe",
    "administrador de tareas": "taskmgr.exe",
    "regedit": "regedit.exe",
    "control panel": "control.exe",
    "panel de control": "control.exe",
    "settings": "ms-settings:",
    "ajustes": "ms-settings:",
    "configuracion": "ms-settings:",
}


# Browsers
_ALIASES.update({
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "edge": "msedge.exe",
    "microsoft edge": "msedge.exe",
    "firefox": "firefox.exe",
    "mozilla firefox": "firefox.exe",
    "brave": "brave.exe",
    "brave browser": "brave.exe",
    "opera": "opera.exe",
    "opera gx": "opera.exe",
})

# Microsoft Office
_ALIASES.update({
    "word": "winword.exe",
    "microsoft word": "winword.exe",
    "excel": "excel.exe",
    "microsoft excel": "excel.exe",
    "powerpoint": "powerpnt.exe",
    "microsoft powerpoint": "powerpnt.exe",
    "outlook": "outlook.exe",
    "onenote": "onenote.exe",
    "teams": "ms-teams:",
    "microsoft teams": "ms-teams:",
})

# Dev tools
_ALIASES.update({
    "vs code": "code",
    "vscode": "code",
    "visual studio code": "code",
    "visual studio": "devenv.exe",
    "android studio": "studio64.exe",
    "intellij": "idea64.exe",
    "intellij idea": "idea64.exe",
    "pycharm": "pycharm64.exe",
    "webstorm": "webstorm64.exe",
    "cursor": "cursor.exe",
    "kiro": "kiro.exe",
    "git bash": "git-bash.exe",
})

# Messaging / Social
_ALIASES.update({
    "whatsapp": "whatsapp:",
    "telegram": "telegram.exe",
    "discord": "discord.exe",
    "signal": "signal.exe",
    "slack": "slack.exe",
    "zoom": "zoom.exe",
    "skype": "skype.exe",
})

# Media
_ALIASES.update({
    "spotify": "spotify.exe",
    "vlc": "vlc.exe",
    "media player": "wmplayer.exe",
    "reproductor de medios": "wmplayer.exe",
    "netflix": "netflix:",
    "youtube": "https://youtube.com",
})

# Gaming
_ALIASES.update({
    "steam": "steam.exe",
    "epic": "EpicGamesLauncher.exe",
    "epic games": "EpicGamesLauncher.exe",
    "epic games launcher": "EpicGamesLauncher.exe",
    "ubisoft": "UbisoftConnect.exe",
    "ubisoft connect": "UbisoftConnect.exe",
    "battle.net": "Battle.net.exe",
    "riot": "RiotClientServices.exe",
    "ea": "EADesktop.exe",
    "ea app": "EADesktop.exe",
    "origin": "Origin.exe",
    "xbox": "xbox:",
})

# Other
_ALIASES.update({
    "obs": "obs64.exe",
    "obs studio": "obs64.exe",
    "photoshop": "photoshop.exe",
    "illustrator": "illustrator.exe",
    "premiere": "Adobe Premiere Pro.exe",
    "after effects": "AfterFX.exe",
    "blender": "blender.exe",
    "figma": "figma.exe",
    "notion": "notion.exe",
    "obsidian": "obsidian.exe",
    "1password": "1password.exe",
    "anydesk": "anydesk.exe",
    "teamviewer": "teamviewer.exe",
})


# --------------------------- Helpers ---------------------------------

_VERB_PREFIX = re.compile(
    r"^(abrime|abrir|abre|open|launch|inicia|iniciar|ejecuta|ejecutar|arranca|arrancar)\s+",
    re.IGNORECASE,
)
_ARTICLE_PREFIX = re.compile(r"^(el|la|los|las|the|un|una)\s+", re.IGNORECASE)
_TRAILING_FLUFF = re.compile(
    r"[\s,]*(por favor|please|gracias|thanks|jarvis)[\s\.\!\?,]*$",
    re.IGNORECASE,
)


def _normalize(name: str) -> str:
    """Lowercase, strip, remove leading verbs/articles, trailing fluff and punctuation."""
    n = (name or "").lower().strip()
    prev = None
    while prev != n:
        prev = n
        n = _TRAILING_FLUFF.sub("", n).strip()
    n = re.sub(r"[\?\!\.\,;:]+$", "", n).strip()
    n = _VERB_PREFIX.sub("", n).strip()
    n = _ARTICLE_PREFIX.sub("", n).strip()
    n = re.sub(r"\s+", " ", n)
    return n


def _is_uri(target: str) -> bool:
    if not target:
        return False
    if target.lower().endswith(".exe"):
        return False
    return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target))


def _try_startfile(target: str) -> bool:
    try:
        os.startfile(target)  # type: ignore[attr-defined]
        return True
    except Exception:
        return False


# Guard lives here, not at each call site: every path that reaches `shell=True`
# (URI step, mapped-exe step, and the raw-name last resort) goes through this
# function, so one check here covers all of them (see plans/ERRORES.md, Fase 04).
_SHELL_METACHARS = re.compile(r'[&|%^<>;]')


def _try_start_command(target: str) -> bool:
    """Use Windows `start` shell command. Resolves App Paths and Store URIs."""
    if _SHELL_METACHARS.search(target):
        return False
    try:
        # Quote target safely; the empty title arg "" is required by `start`.
        safe = target.replace('"', '')
        subprocess.Popen(
            f'start "" "{safe}"',
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False


def _lookup_app_paths(exe_name: str):
    """Search HKCU and HKLM `App Paths` for the executable's full path."""
    if sys.platform != "win32":
        return None
    try:
        import winreg  # type: ignore
    except ImportError:
        return None

    if not exe_name.lower().endswith(".exe"):
        exe_name = exe_name + ".exe"

    sub = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\\" + exe_name
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, sub) as key:
                value, _ = winreg.QueryValueEx(key, "")
                if value and Path(value).exists():
                    return value
        except OSError:
            continue
    return None


# Caché de proceso: se llena una sola vez con el primer escaneo y se
# reutiliza para toda la vida del proceso. Se pierde al reiniciar Jarvis
# (aceptable, ver plans/phase-12-tools-async.md) — instalar una app nueva
# requiere reiniciar para que _scan_start_menu la vea.
_START_MENU_CACHE: list | None = None


def _load_start_menu_entries() -> list:
    """Escanea las carpetas de Menú Inicio una sola vez y devuelve la lista
    cacheada de (stem_lowercase, ruta)."""
    global _START_MENU_CACHE
    if _START_MENU_CACHE is not None:
        return _START_MENU_CACHE

    entries = []
    roots = [
        Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs",
        Path(os.environ.get("ProgramData", "")) / r"Microsoft\Windows\Start Menu\Programs",
    ]
    for root in roots:
        if not root or not root.exists():
            continue
        try:
            for lnk in root.rglob("*.lnk"):
                entries.append((lnk.stem.lower(), str(lnk)))
        except Exception:
            continue
    _START_MENU_CACHE = entries
    return entries


def _scan_start_menu(name: str):
    """Fuzzy-search Start Menu shortcuts (.lnk) for a matching app name."""
    needle = (name or "").lower().strip()
    if not needle:
        return None
    candidates = []
    for stem, path in _load_start_menu_entries():
        if needle == stem:
            return path
        if needle in stem or stem in needle:
            score = abs(len(stem) - len(needle))
            candidates.append((score, path))
    if candidates:
        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]
    return None


# --------------------------- Main entrypoint -------------------------

def open_app(parameters: dict, response=None, player=None) -> str:
    """Launch a desktop application by spoken name."""
    raw = (parameters or {}).get("app_name", "") or ""
    if not raw.strip():
        return "App name is required, sir."

    name = _normalize(raw)
    if not name:
        return "App name is required, sir."

    target = _ALIASES.get(name, name)

    def _log(msg: str) -> None:
        if player and hasattr(player, "write_log"):
            try:
                player.write_log(msg)
            except Exception:
                pass

    # 1. URI scheme (ms-settings:, whatsapp:, https://, etc.)
    if _is_uri(target):
        if _try_startfile(target) or _try_start_command(target):
            _log(f"Opening {raw}")
            return f"Opening {raw}, sir."
        return f"Failed to open '{raw}', sir."

    # 2. Plain executable on PATH
    exe_on_path = shutil.which(target)
    if not exe_on_path and not target.lower().endswith(".exe"):
        exe_on_path = shutil.which(target + ".exe")
    if exe_on_path:
        try:
            subprocess.Popen([exe_on_path])
            _log(f"Opening {raw}")
            return f"Opening {raw}, sir."
        except Exception:
            pass

    # 3. Registry App Paths (covers Chrome, Spotify, etc. installed per-user)
    reg_path = _lookup_app_paths(target)
    if reg_path and _try_startfile(reg_path):
        _log(f"Opening {raw}")
        return f"Opening {raw}, sir."

    # 4. Windows `start` with the mapped target if it looks like a real exe path
    if (target.lower().endswith(".exe") or "\\" in target or "/" in target):
        if _try_start_command(target):
            _log(f"Opening {raw}")
            return f"Opening {raw}, sir."

    # 5. Start Menu shortcut scan (covers VS Code, Discord, Steam, Word, etc.
    #    even when not on PATH or registered).
    lnk = _scan_start_menu(name)
    if lnk and _try_startfile(lnk):
        _log(f"Opening {raw}")
        return f"Opening {raw}, sir."

    # Also try a shortcut scan using the alias target's stem (e.g. "code", "winword")
    if target and target != name:
        stem = Path(target).stem
        if stem and stem.lower() != name:
            lnk2 = _scan_start_menu(stem)
            if lnk2 and _try_startfile(lnk2):
                _log(f"Opening {raw}")
                return f"Opening {raw}, sir."

    # 6. Last-resort: try `start` with the raw normalized name. Some apps register
    #    by display name in protocol handlers.
    if _try_start_command(name):
        _log(f"Trying to open {raw}")
        return f"Opening {raw}, sir."

    return f"I couldn't find '{raw}' on this system, sir."
