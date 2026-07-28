# Fase 02 — Gestor de tareas + matcher local

## Objetivo

Portar el gestor de tareas (pendientes/hechas, con fecha y hora en lenguaje
natural) del proyecto de referencia HRZ, y agregar un matcher local por
regex/keywords que resuelva las acciones de tareas SIN llamar a ninguna API
de IA.

## Contexto

Depende de la **Fase 01** (usa `Jarvis/app/config.py` solo si hiciera falta
leer configuración; en la práctica este módulo no necesita config, es
autónomo). No depende de Gemini ni de voz — este módulo se puede probar
100% por texto/consola.

Fuente de referencia (leer antes de escribir código):
`JARVIS-HRZ proyecto para clonar o copiar inspirarse y mejorar/_internal/actions/tareas.py`
(396 líneas, ya revisado en la conversación de diseño — es un módulo sólido,
con parseo de fechas en lenguaje natural español: "hoy", "mañana", "el
lunes", "11 de julio", etc., y persistencia en JSON con lock de threading).

## Alcance de esta fase

### 1. Copiar y adaptar `tareas.py`

Crear `Jarvis/app/actions/tareas.py` a partir del archivo de referencia,
con estos cambios respecto al original:

- Cambiar las rutas: en el original,
  `BASE_DIR = Path(__file__).resolve().parent.parent` y
  `TAREAS_PATH = BASE_DIR / "datos" / "tareas.json"`. Mantener ese mismo
  esquema relativo (2 niveles arriba de `actions/`, carpeta `datos/`), que
  ya coincide con la estructura creada en la Fase 01
  (`Jarvis/datos/tareas.json`).
- Quitar cualquier parámetro `player=None` que solo se use para
  `player.write_log(...)` (eso era para la UI del HRZ, que no existe
  todavía — dejar la función `tareas(parameters, player=None)` aceptando
  `player` opcional iguel, pero no depender de que exista hasta la Fase 08).
- El resto de la lógica (creación, edición, completado, borrado, parseo de
  fechas, formateo de "hoy/mañana/el próximo lunes") se mantiene igual, es
  código ya probado.

### 2. Matcher local

Crear `Jarvis/app/matcher.py` con una función:

```python
def match_local(texto: str) -> dict | None:
    """
    Intenta resolver `texto` con reglas locales (sin IA).
    Devuelve un dict {"tool": "tareas", "parameters": {...}} si matchea,
    o None si no matchea ningún patrón conocido (en ese caso, el llamador
    debe escalar a Gemini — eso lo conecta la Fase 05).
    """
```

Reglas a implementar para tareas (case-insensitive, español, con variantes
razonables):

| Frase de ejemplo | Acción resuelta |
|---|---|
| "agregar tarea comprar pan mañana" / "nueva tarea ..." / "recuérdame que tengo que ..." | `tareas` action=`add` — extraer descripción y fecha con regex simple (buscar palabras clave de fecha: hoy/mañana/lunes.../dd de mes) |
| "marca como hecha ..." / "completa la tarea ..." / "ya hice ..." | `tareas` action=`complete`, description=resto del texto |
| "qué tareas tengo" / "mis pendientes" / "qué tengo que hacer" | `tareas` action=`list` |
| "elimina la tarea ..." / "borra la tarea ..." | `tareas` action=`delete`, description=resto del texto |

El matcher NO necesita ser perfecto ni cubrir cada variante posible de
lenguaje — su trabajo es cubrir los casos comunes y devolver `None` en
cualquier caso ambiguo, para que la Fase 05 lo mande a Gemini como
fallback. Priorizar precisión (no ejecutar la acción equivocada) sobre
cobertura total.

Estructura del archivo: usar una lista de tuplas
`(regex_compilado, funcion_extractora)` iterada en orden, similar a como
`open_app.py` normaliza texto con regex (`_VERB_PREFIX`, `_ARTICLE_PREFIX`
en
`JARVIS-HRZ proyecto para clonar o copiar inspirarse y mejorar/_internal/actions/open_app.py`
líneas 155–177) — reutilizar esa técnica de normalización de texto
(quitar verbos tipo "agrega/agregar/pon", artículos, y coletillas como
"por favor", "gracias").

## Fuera de alcance

- No conectar todavía con voz ni con Gemini (eso es Fase 05/06).
- No crear interfaz gráfica para tareas todavía (eso es Fase 08).

## Verificación

Script `Jarvis/app/actions/_check_tareas.py` (o bloque
`if __name__ == "__main__":`) que sin ningún mock:

1. Crea una tarea nueva vía `tareas({"action": "add", "description": "probar sistema", "date": "mañana"})`.
2. Lista tareas y confirma que aparece.
3. La marca como completada.
4. Confirma con `match_local("qué tareas tengo")` que devuelve
   `{"tool": "tareas", "parameters": {"action": "list"}}`.
5. Confirma que `match_local("cuéntame un chiste")` devuelve `None`
   (no debe confundir texto no relacionado con una acción de tareas).
6. Imprime `OK` o el detalle del fallo.

## Entregable final de la fase

- `Jarvis/app/actions/tareas.py` funcionando de forma standalone.
- `Jarvis/app/matcher.py` con reglas de tareas.
- Self-check pasando.
- Marcar `- [x] Fase 02` en `plans/README.md`.
