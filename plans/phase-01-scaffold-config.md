# Fase 01 — Scaffold del proyecto + módulo de configuración

## Objetivo

Crear la nueva estructura de carpetas del asistente y un módulo de
configuración local (API key de Gemini, voz elegida, dispositivo de
mic/altavoz, ubicación) que el resto de las fases van a leer y escribir.
Esta fase NO agrega funcionalidad de voz ni de IA todavía — solo la base.

## Contexto

Repo actual: `Jarvis-Desktop-Voice-Assistant`. Ya existe `Jarvis/jarvis.py`
(versión simple original, en inglés, con customtkinter — **no tocar ni
borrar**, se mantiene intacto como referencia histórica del proyecto
original). La nueva versión vive en subcarpetas nuevas dentro de `Jarvis/`.

No hay todavía ningún requirements.txt para la nueva versión — hay que crear
uno separado o extender el existente (decisión: extender el
`requirements.txt` raíz, agregando las dependencias nuevas al final, sin
borrar las que ya están, porque `jarvis.py` original las sigue necesitando).

## Alcance de esta fase

Crear:

```
Jarvis/
  app/
    __init__.py
    config.py
  datos/              (vacía, con .gitkeep — la usarán fases futuras para JSON)
  assets/             (vacía, con .gitkeep — la usará la fase 08 para HTML/CSS/JS)
```

### `Jarvis/app/config.py`

Módulo de configuración local, sin dependencias externas nuevas (solo
stdlib: `json`, `pathlib`). Debe exponer:

```python
DEFAULTS = {
    "gemini_api_key": "",
    "voice": "Puck",
    "mic_device_index": -1,       # -1 = predeterminado del sistema
    "speaker_device_index": -1,   # -1 = predeterminado del sistema
    "location": "",               # ciudad o "lat,lon" — la usa fase 07 (clima)
}

VOCES_DISPONIBLES = [
    "Aoede", "Charon", "Fenrir", "Kore",
    "Puck", "Orus", "Leda", "Zephyr",
]

def load_settings() -> dict: ...
def save_settings(data: dict) -> None: ...
def get(key: str, default=None): ...
def set(key: str, value) -> None: ...
```

Comportamiento:

- Los settings se guardan en `Jarvis/datos/settings.json`.
- `load_settings()` crea el archivo con `DEFAULTS` si no existe, y si existe
  pero le faltan claves nuevas (por ejemplo si una fase futura agrega una
  clave a `DEFAULTS`), las completa con el default sin pisar las que ya
  tiene el usuario guardadas (merge, no overwrite).
- `save_settings(data)` valida que `data["voice"]` esté en
  `VOCES_DISPONIBLES` (si no, ignora ese campo y mantiene el valor previo).
- Debe ser seguro para llamadas concurrentes (usar un `threading.Lock`,
  igual que hace `tareas.py`/`recordatorios.py` del proyecto de referencia
  HRZ — ver ese patrón en
  `JARVIS-HRZ proyecto para clonar o copiar inspirarse y mejorar/_internal/actions/tareas.py`
  líneas 135–157, es el mismo patrón de lock + load + save que hay que
  replicar aquí).
- Sin encriptación de la API key — es uso personal, JSON plano es
  suficiente (decisión ya tomada, no reabrir este tema).

### `.gitignore`

Agregar `Jarvis/datos/settings.json` al `.gitignore` raíz (no versionar la
API key del usuario). Mantener el resto del `.gitignore` existente intacto.

## Fuera de alcance (no hacer en esta fase)

- No crear todavía la interfaz gráfica (eso es fase 08).
- No integrar Gemini todavía.
- No crear el archivo `main.py` de arranque todavía — eso lo arma la fase
  05 cuando haya algo real que arrancar.

## Verificación

Dejar un self-check ejecutable simple (no framework de test, solo un
`if __name__ == "__main__":` en `config.py` o un script chico
`Jarvis/app/_check_config.py`) que:

1. Llama `load_settings()`, confirma que devuelve todas las claves de
   `DEFAULTS`.
2. Llama `save_settings({"voice": "Kore"})`, vuelve a cargar y confirma que
   `get("voice") == "Kore"`.
3. Llama `save_settings({"voice": "NoExiste"})`, confirma que la voz
   guardada sigue siendo `"Kore"` (la inválida se ignoró).
4. Imprime `OK` si los 3 checks pasan, o el detalle del que falló.

## Entregable final de la fase

- Carpetas creadas.
- `Jarvis/app/config.py` funcionando según lo descrito.
- `.gitignore` actualizado.
- Self-check corrido manualmente y mostrando `OK`.
- Marcar `- [x] Fase 01` en `plans/README.md`.
