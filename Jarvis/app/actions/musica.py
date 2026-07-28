"""musica.py — Reproducir música buscando en YouTube (sin API key, sin
Spotify OAuth) más control genérico de reproducción vía teclas multimedia.

Adaptado de JARVIS-HRZ `_internal/actions/spotify_control.py` (control de
teclas multimedia, Fase 04 del plan).
"""
import webbrowser

# ponytail: youtube-search-python puede romperse si YouTube cambia su API
# interna; si falla, reemplazar por scraping directo de
# youtube.com/results?search_query= con requests+regex sobre "videoId"


def buscar_youtube(query: str) -> dict | None:
    """Busca `query` en YouTube y devuelve el primer resultado, o None si
    no encontró nada o la búsqueda falló."""
    query = (query or "").strip()
    if not query:
        return None
    try:
        from youtubesearchpython import VideosSearch
        resultados = VideosSearch(query, limit=1).result()
        items = resultados.get("result", [])
        if not items:
            return None
        primero = items[0]
        titulo = primero.get("title", "")
        url = primero.get("link", "")
        if not titulo or not url:
            return None
        return {"title": titulo, "url": url}
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
        webbrowser.open(resultado["url"])
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
