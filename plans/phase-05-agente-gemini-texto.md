# Fase 05 — Agente Gemini de texto (function-calling) + búsqueda con grounding

## Objetivo

Construir el "cerebro" del asistente: un agente que recibe texto (venga de
voz-a-texto o de teclado), primero intenta resolverlo con el matcher local
(fases 02–04, gratis), y si no matchea nada, lo manda a Gemini con
function-calling para que decida qué herramienta ejecutar — incluyendo una
herramienta de búsqueda web real (con grounding, para que el agente lea
resultados de verdad, no solo abra un navegador a ciegas).

## Contexto

Depende de las **Fases 01, 02, 03, 04** (usa `config.py` para la API key,
y expone como tools los módulos `tareas`, `recordatorios`, `open_app`,
`musica` ya construidos). Esta fase es la primera que efectivamente llama
a la API de Gemini y por lo tanto la primera que consume cuota — probarla
con moderación.

Decisión ya tomada con el usuario: usar la **API directa de Google**
(paquete `google-genai`), NO OpenRouter (el HRZ usaba OpenRouter como
intermediario — acá no aplica, evitamos ese intermediario y su cuota
aparte). Modelo por defecto: `gemini-2.5-flash` para razonar,
`gemini-2.0-flash-lite` como opción más barata configurable. **Importante:**
los nombres exactos de modelo disponibles cambian con el tiempo — antes de
hardcodear un modelo, listar los modelos disponibles con
`client.models.list()` y confirmar que el nombre elegido sigue existiendo;
si no, tomar el equivalente vigente más parecido (misma familia "flash",
más barato/rápido posible).

## Alcance de esta fase

### 1. Dependencia nueva

Agregar a `requirements.txt`: `google-genai`.

### 2. Módulo del agente

Crear `Jarvis/app/gemini_agent.py`:

```python
class GeminiAgent:
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"): ...
    def procesar(self, texto: str, player=None) -> str:
        """
        1. Intenta match_local(texto). Si matchea, ejecuta la tool
           directamente (sin llamar a Gemini) y devuelve el resultado.
        2. Si no matchea, llama a Gemini con function-calling declarando
           las tools disponibles (tareas, recordatorios, open_app, musica,
           buscar_web). Ejecuta la/las tool call(s) que el modelo pida,
           le devuelve el resultado, y retorna la respuesta final en texto
           natural del modelo.
        """
```

### 3. Declaración de tools para Gemini

**Antes de declarar `open_app` como tool**: endurecer
`Jarvis/app/actions/open_app.py`. La revisión de la Fase 04 encontró que
el último recurso de `_try_start_command` (paso 6, cuando `app_name` no
matcheó ningún alias/acceso directo) pasa el texto normalizado del
usuario directo a `shell=True` sin allowlist — hoy es seguro solo porque
`cmd.exe` respeta el quoting de `f'start "" "{safe}"'` (verificado
empíricamente, ver `plans/ERRORES.md`, entrada Fase 04), no por una
garantía de diseño. Con function-calling, `app_name` puede ser lo que
Gemini decida escribir a partir del prompt del usuario — endurecer ANTES
de exponerlo: rechazar (no ejecutar, devolver mensaje de error) cualquier
`app_name` que contenga metacaracteres de shell (`&`, `|`, `%`, `^`, `<`,
`>`, `;`) antes de llegar a `_try_start_command`, en vez de confiar en el
quoting. Esto es un requisito de esta fase, no opcional.

Cada acción existente (`tareas`, `recordatorios`, `open_app`, `musica`) se
declara como function-calling tool con su schema de parámetros (usar los
mismos nombres de acciones/parámetros ya definidos en las fases 02–04, no
inventar unos nuevos). Agregar una tool nueva:

```python
def buscar_web(parameters: dict, player=None) -> str:
    """
    Usa el grounding de búsqueda de Google integrado en la API de Gemini
    (herramienta `google_search` / equivalente vigente al momento de
    implementar — confirmar el nombre exacto en la documentación actual
    del SDK `google-genai`, cambió de nombre entre versiones del SDK).
    Devuelve un resumen en texto de lo que el modelo encontró, con fuentes
    si el grounding las expone.
    """
```

Esta tool es la que reemplaza el patrón "abre el navegador pero no lee
nada" que tenía `browser_control.py` en el HRZ — acá Gemini SÍ procesa el
contenido encontrado antes de responder. Opcionalmente (no obligatorio en
esta fase), después de responder con la info real, se puede además abrir
el navegador con la misma query solo como efecto visual — dejarlo como
parámetro opcional `abrir_navegador: bool = False` en `buscar_web`, no
como comportamiento por defecto.

### 4. Conectar el `action_prompt` pendiente de la Fase 03

En `Jarvis/app/actions/recordatorios.py` quedó un
`# TODO fase-05:` en `_disparar()` donde una alarma con `action_prompt`
solo se leía en voz sin ejecutarse. En esta fase, reemplazar eso: cuando
dispara una alarma con `action_prompt` no vacío, en vez de solo leerlo,
pasarlo a `GeminiAgent.procesar(action_prompt)` y hablar la respuesta que
devuelva (así "que Jarvis me diga las noticias cuando suene la alarma" 
funciona de verdad).

### 5. Sistema de fallback y logging de cuota

Agregar un contador simple en memoria (no persistente, no hace falta) de
cuántas veces se llamó a Gemini en la sesión actual vs. cuántas veces se
resolvió por matcher local, y exponerlo en un método
`GeminiAgent.stats() -> dict` (ej. `{"local": 12, "gemini": 3}`). Esto es
para que la futura interfaz (Fase 08) pueda mostrarlo si se quiere, y para
que el usuario pueda confirmar en la práctica que el ahorro de cuota
funciona.

## Fuera de alcance

- No conectar voz todavía (eso es Fase 06) — esta fase se prueba pasando
  strings de texto directamente, simulando lo que en el futuro vendrá del
  reconocimiento de voz.
- No crear interfaz gráfica (Fase 08).
- No implementar clima/morning brief todavía (Fase 07) aunque esta fase
  deje el agente listo para que la Fase 07 le agregue esas tools después.

## Verificación

Self-check (`Jarvis/app/_check_agente.py`), **usando la API key real del
usuario** (advertencia: este check sí consume cuota, correrlo una sola vez,
no en loop):

1. `agente.procesar("qué tareas tengo")` → confirmar que se resolvió por
   matcher local (`agente.stats()["gemini"] == 0` después de esta llamada).
2. `agente.procesar("recomiéndame qué hacer un día lluvioso en casa")` →
   confirmar que esta sí escaló a Gemini (`stats()["gemini"] == 1`) y que
   la respuesta no está vacía.
3. `agente.procesar("busca qué pasó hoy con el precio del bitcoin")` →
   confirmar que la respuesta contiene información concreta (no un genérico
   "no tengo acceso a internet en tiempo real" — si responde eso, el
   grounding no está bien configurado y hay que revisar el nombre de la
   tool de búsqueda contra la documentación vigente del SDK).
4. Imprimir `OK` con el detalle de `stats()` al final.

## Entregable final de la fase

- `Jarvis/app/gemini_agent.py` funcionando con function-calling real sobre
  las 4 tools existentes + `buscar_web` con grounding.
- `action_prompt` de alarmas ahora se ejecuta de verdad, no solo se lee.
- Contador de uso local vs. Gemini disponible vía `stats()`.
- `requirements.txt` actualizado.
- Marcar `- [x] Fase 05` en `plans/README.md`.
