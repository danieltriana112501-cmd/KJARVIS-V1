# Fase 04 — Abrir aplicaciones + reproducir música

## Objetivo

Portar el lanzador de aplicaciones del proyecto de referencia HRZ (módulo
robusto, no necesita cambios de fondo) y construir el módulo de música:
buscar una canción en YouTube (sin API key, sin apps de escritorio) y
abrirla en el navegador, más control de reproducción genérico vía teclas
multimedia del sistema operativo.

## Contexto

Depende de **Fase 01**. Independiente de las Fases 02/03 (se puede hacer
en paralelo). Decisión ya tomada con el usuario: **no** integrar la app de
escritorio de Spotify (requiere OAuth, complejidad innecesaria) — la
música se resuelve buscando en YouTube y abriendo el navegador.

## Alcance de esta fase

### 1. Copiar `open_app.py` casi sin cambios

Fuente:
`JARVIS-HRZ proyecto para clonar o copiar inspirarse y mejorar/_internal/actions/open_app.py`
(340 líneas). Es un módulo autocontenido y ya robusto: mapea alias
español/inglés a ejecutables, prueba `os.startfile`, registro de Windows
(`App Paths`), comando `start`, y escaneo de accesos directos del menú
inicio como último recurso.

Copiar tal cual a `Jarvis/app/actions/open_app.py`. Único cambio: la
docstring de módulo puede quedar igual, no hace falta tocar nada de la
lógica interna — es el módulo que menos cambios necesita de todo el
proyecto de referencia.

Verificar que ninguna rama de código use `subprocess.run(..., shell=True)`
con un string sin sanear proveniente del usuario/LLM sin pasar por la
tabla `_ALIASES` — revisando el original, `_try_start_command` arma el
comando con el `target` ya resuelto por alias o por regex de normalización,
no ejecuta texto arbitrario de una frase completa del usuario. Confirmar
esto se mantiene así tras copiar (no relajar esa validación).

### 2. Módulo de música

Crear `Jarvis/app/actions/musica.py`:

```python
def buscar_youtube(query: str) -> dict | None:
    """Busca `query` en YouTube y devuelve {"title": ..., "url": ...} del
    primer resultado, o None si no encontró nada / falló la búsqueda."""

def musica(parameters: dict, player=None) -> str:
    """
    Acciones: play | pause | next | prev | volume
    - play: requiere parameters["query"], busca en YouTube y abre el video
      con webbrowser.open(...).
    - pause/next/prev/volume: usa teclas multimedia del SO (no dependen de
      qué esté sonando — Spotify, YouTube, lo que sea que tenga foco).
    """
```

Para `buscar_youtube`, usar el paquete `youtube-search-python`
(instalar y agregar a `requirements.txt`: `youtube-search-python`) —
no requiere API key, no requiere login. Ejemplo de uso mínimo:

```python
from youtubesearchpython import VideosSearch
resultados = VideosSearch(query, limit=1).result()
```

Si esa librería falla en el entorno (dejar de funcionar por cambios de
YouTube es un riesgo conocido y aceptado — dejar un comentario
`# ponytail: youtube-search-python puede romperse si YouTube cambia su API
interna; si falla, reemplazar por scraping directo de
youtube.com/results?search_query= con requests+regex sobre "videoId"`),
capturar la excepción y devolver `None`, y que `musica()` responda un
mensaje de error legible en vez de crashear.

Para `pause/next/prev/volume`, reutilizar la técnica de
`spotify_control.py` del HRZ
(`JARVIS-HRZ proyecto para clonar o copiar inspirarse y mejorar/_internal/actions/spotify_control.py`,
39 líneas, ya revisado) — usa `pyautogui.press("playpause"/"nexttrack"/
"prevtrack"/"volumeup"/"volumedown")`, teclas multimedia estándar de
Windows que cualquier reproductor con foco (o incluso sin foco, en muchos
casos) recibe. Copiar esa lógica dentro de `musica()` en vez de mantener
dos módulos separados — no hace falta un archivo aparte para esto, es una
sola función.

### 3. Matcher local

Extender `Jarvis/app/matcher.py` (de la Fase 02):

| Frase de ejemplo | Acción resuelta |
|---|---|
| "abre/abrime [app]" / "abrir [app]" / "ejecuta [app]" | `open_app`, app_name=resto del texto tras quitar el verbo (reutilizar `_normalize` de `open_app.py`, ya hace este trabajo — exponerla como función pública si hace falta) |
| "pon/reproduce/toca [canción]" | `musica` action=`play`, query=resto del texto |
| "pausa/pausar (la música)" | `musica` action=`pause` |
| "siguiente canción" / "salta esta canción" | `musica` action=`next` |
| "canción anterior" | `musica` action=`prev` |
| "sube/baja el volumen" | `musica` action=`volume`, value=`up`/`down` |

## Fuera de alcance

- No conectar con Gemini todavía (Fase 05).
- No hay interfaz gráfica para esto (no la necesita — es control directo).
- No se agrega ningún backend de Spotify con API/OAuth (descartado).

## Verificación

Self-check (`Jarvis/app/actions/_check_apps_musica.py`):

1. Llama `open_app({"app_name": "bloc de notas"})` y confirma visualmente
   (manual, no automatizable sin ver pantalla) que se abre Notepad.
2. Llama `buscar_youtube("lofi hip hop radio")` y confirma que devuelve un
   dict con `title` y `url` no vacíos.
3. Confirma `match_local("abre calculadora")` devuelve
   `{"tool": "open_app", "parameters": {"app_name": "calculadora"}}`.
4. Confirma `match_local("pon bohemian rhapsody")` devuelve
   `{"tool": "musica", "parameters": {"action": "play", "query": "bohemian rhapsody"}}`.
5. Imprime `OK` o detalle del fallo (los pasos 1 y 2 requieren confirmación
   humana ya que abren ventanas/navegador reales — dejarlo documentado en
   la salida del script, no intentar automatizar esa verificación).

## Entregable final de la fase

- `Jarvis/app/actions/open_app.py` copiado y funcionando.
- `Jarvis/app/actions/musica.py` funcionando.
- `requirements.txt` actualizado con `youtube-search-python` y
  `pygetwindow` si hiciera falta (revisar si `open_app.py` la necesita —
  no, esa la usa `browser_control.py` que NO se porta en esta fase).
- Reglas agregadas a `Jarvis/app/matcher.py`.
- Marcar `- [x] Fase 04` en `plans/README.md`.
