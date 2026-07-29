"""musica.py — Reproducir música buscando en YouTube (sin API key, sin
Spotify OAuth) más control genérico de reproducción vía teclas multimedia.

Adaptado de JARVIS-HRZ `_internal/actions/spotify_control.py` (control de
teclas multimedia, Fase 04 del plan) y `_internal/actions/youtube_video.py`
(scraping de YouTube, Fase 16 del plan — reemplaza el `youtube-search-python`
original, sin mantener y con un pin de `httpx` que bloqueaba actualizar
`google-genai`, ver plans/ERRORES.md).
"""
import re
import urllib.parse
import urllib.request

from app.actions.navegador import abrir_url

_VIDEO_ID_RE = re.compile(r'"videoId":"([a-zA-Z0-9_-]{11})"')


def buscar_youtube(query: str) -> dict | None:
    """Busca `query` en YouTube (scraping de la página de resultados, sin
    dependencias externas) y devuelve el primer video, o None si no
    encontró nada o la búsqueda falló."""
    query = (query or "").strip()
    if not query:
        return None
    try:
        url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        match = _VIDEO_ID_RE.search(html)
        if not match:
            return None
        return {"title": query, "url": f"https://www.youtube.com/watch?v={match.group(1)}"}
    except Exception as e:
        print(f"[Musica] Error buscando en YouTube: {e}")
        return None


def musica(parameters: dict, player=None) -> str:
    """Controla la reproducción de música.

    Acciones: play | pause | next | prev | volume
    - play: busca `parameters["query"]` en YouTube y lo abre en el navegador.
    - pause/next/prev/volume: usa teclas multimedia del sistema, funcionan
      con cualquier reproductor que tenga el foco (Spotify, YouTube, etc.).
    """
    action = str(parameters.get("action", "")).lower().strip()

    def _log(msg: str) -> None:
        if player and hasattr(player, "write_log"):
            try:
                player.write_log(msg)
            except Exception:
                pass

    if action == "play":
        query = str(parameters.get("query", "")).strip()
        if not query:
            return "Necesito el nombre de una canción, señor."
        resultado = buscar_youtube(query)
        if not resultado:
            return f"No pude encontrar '{query}' en YouTube, señor."
        abrir_url(resultado["url"])
        _log(f"Reproduciendo: {resultado['title']}")
        return f"Reproduciendo '{resultado['title']}', señor."

    try:
        import pyautogui
    except Exception as e:
        return f"No pude controlar la reproducción: {e}"

    if action == "pause":
        pyautogui.press("playpause")
        msg = "Reproducción pausada, señor."
    elif action == "next":
        pyautogui.press("nexttrack")
        msg = "Siguiente canción, señor."
    elif action == "prev":
        pyautogui.press("prevtrack")
        msg = "Canción anterior, señor."
    elif action == "volume":
        value = str(parameters.get("value", "")).lower()
        if "up" in value or "sub" in value:
            pyautogui.press("volumeup", presses=5)
            msg = "Volumen subido, señor."
        elif "down" in value or "baj" in value:
            pyautogui.press("volumedown", presses=5)
            msg = "Volumen bajado, señor."
        else:
            msg = f"Necesito 'up' o 'down' para el volumen, señor."
    else:
        msg = f"Acción de música '{action}' no soportada."

    _log(msg)
    return msg


def _check() -> None:
    resultado = buscar_youtube("lofi hip hop radio")
    assert resultado is not None, "buscar_youtube no devolvió resultado"
    assert resultado["title"], "título vacío"
    assert resultado["url"], "url vacía"

    sin_query = musica({"action": "play", "query": ""})
    assert "necesito" in sin_query.lower(), f"no pidió query: {sin_query}"

    print("OK")


if __name__ == "__main__":
    _check()
