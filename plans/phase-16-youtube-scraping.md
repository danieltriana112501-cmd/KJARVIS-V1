# Fase 16 — YouTube sin `youtube-search-python`, ruteo correcto a `musica`

## Objetivo

Dos bugs reales encontrados probando voz en vivo:

1. **`buscar_youtube()` depende de `youtube-search-python`**, paquete sin
   mantener, ya documentado como frágil (`plans/ERRORES.md`, Fases 04/05) y
   con un pin de `httpx` que bloquea actualizar `google-genai`.
2. **El modelo rutea pedidos de YouTube a `buscar_web` en vez de `musica`**
   (visto en log real: *"Busca y coloca la primer canción en YouTube de
   Bat Bunny"* → `tool_call: buscar_web(...)`). `buscar_web` usa grounding
   de Google con cuota limitada (429 documentado, Fase 05) — para YouTube
   es la tool equivocada Y la que menos cuota tiene.

## Contexto

El proyecto de referencia `JARVIS-HRZ` (`_internal/actions/youtube_video.py`)
ya resuelve esto sin dependencias: scraping directo de
`youtube.com/results?search_query=` con `urllib` + regex sobre `"videoId"`.
Es exactamente la salida de emergencia que la nota `ponytail` de
`musica.py:9-11` ya anticipaba.

## Alcance de esta fase

### 1. Reemplazar `buscar_youtube()` en `musica.py`

Usar `urllib.request` + regex (`r'"videoId":"([a-zA-Z0-9_-]{11})"'`) sobre
`https://www.youtube.com/results?search_query=<query>`, con
`User-Agent: Mozilla/5.0` (sin eso YouTube puede devolver una página
distinta). Sin `requests`, sin `youtube-search-python` — `urllib` es
stdlib. Devolver `{"title": query, "url": ...}` (no hay título real fácil
de sacar solo del regex de `videoId` sin parsear más HTML — usar el query
tal cual como "title" alcanza para el mensaje de confirmación; si se quiere
título real, extraerlo del mismo HTML con otro regex, pero no es
obligatorio para esta fase).

### 2. Sacar `youtube-search-python` de `requirements.txt`

Y confirmar que sacar el pin de `httpx<0.28` (si estaba solo por esto) no
rompe nada — correr `python -c "import google.genai"` después.

### 3. Afinar la descripción de la tool `musica` para que el modelo la elija

En `gemini_agent.py`, la descripción de `musica` debe dejar explícito que
cubre "buscar y reproducir videos/canciones de YouTube" para que el modelo
no vaya a `buscar_web` para esto. Ajustar también la descripción de
`buscar_web` para aclarar que NO es para YouTube/música (evitar que gane
la ambigüedad).

## Fuera de alcance

- Sacar título real del video (queda con el query tal cual).
- Cambiar `buscar_web` en sí (su propio 429 de cuota es un problema de
  billing, no de código, ya documentado).
- Tocar `open_app` o cualquier otra tool.

## Verificación

1. `python -c "from app.actions.musica import buscar_youtube; print(buscar_youtube('lofi hip hop radio'))"` devuelve una URL real de YouTube.
2. `python app/actions/musica.py` (self-check existente) pasa.
3. `python -c "import google.genai"` sin error tras sacar el pin de `httpx` (si aplica).
4. Manual: pedir por voz "buscá y poné un video de X en YouTube" y confirmar que el modelo llama a `musica`, no a `buscar_web`.

## Entregable final de la fase

- `buscar_youtube()` sin dependencia externa, vía scraping stdlib.
- `youtube-search-python` fuera de `requirements.txt`.
- Descripciones de `musica`/`buscar_web` afinadas para ruteo correcto.
- Marcar `- [x] Fase 16` en `plans/README.md`.
