"""gemini_agent.py — Agente de texto: matcher local primero (gratis), Gemini
con function-calling si no matchea, con una tool de búsqueda real con
grounding de Google integrado en la API.

API directa de Google (`google-genai`), no OpenRouter. `buscar_web` hace su
propia llamada a Gemini con la tool `google_search` en una request separada
de la de function-calling: la API rechaza mezclar `google_search` con
`function_declarations` propias en la misma request (probado contra la
librería instalada, ver `plans/ERRORES.md`).
"""
from __future__ import annotations

from urllib.parse import quote

from google import genai
from google.genai import types

from app.matcher import match_local
from app.actions.tareas import tareas as _tareas
from app.actions.recordatorios import recordatorios as _recordatorios
from app.actions.open_app import open_app as _open_app
from app.actions.musica import musica as _musica

_TAREAS_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["list", "add", "edit", "complete", "delete"]},
        "description": {"type": "string"},
        "date": {"type": "string", "description": "Fecha en lenguaje natural o YYYY-MM-DD"},
        "time": {"type": "string", "description": "Hora HH:MM"},
        "task_id": {"type": "string"},
    },
    "required": ["action"],
}

_RECORDATORIOS_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["list", "add", "delete"]},
        "message": {"type": "string"},
        "when": {
            "type": "string",
            "description": "Cuándo dispara, en lenguaje natural (ej. 'en 10 minutos', 'mañana a las 8')",
        },
        "time": {"type": "string"},
        "kind": {"type": "string", "enum": ["reminder", "alarm"]},
        "recurrence": {"type": "string", "enum": ["none", "daily", "weekly", "weekdays"]},
        "action_prompt": {
            "type": "string",
            "description": "Solo para alarmas: instrucción a ejecutar cuando suene (ej. 'dame las noticias')",
        },
        "id": {"type": "string"},
    },
    "required": ["action"],
}

_OPEN_APP_SCHEMA = {
    "type": "object",
    "properties": {
        "app_name": {"type": "string"},
    },
    "required": ["app_name"],
}

_MUSICA_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["play", "pause", "next", "prev", "volume"]},
        "query": {"type": "string"},
        "value": {"type": "string", "enum": ["up", "down"]},
    },
    "required": ["action"],
}

_BUSCAR_WEB_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string"},
        "abrir_navegador": {
            "type": "boolean",
            "description": "Además de responder con la info encontrada, abrir el navegador con la misma búsqueda. Por defecto false.",
        },
    },
    "required": ["query"],
}

_DISPATCH = {
    "tareas": _tareas,
    "recordatorios": _recordatorios,
    "open_app": _open_app,
    "musica": _musica,
}

_MAX_TURNOS_FUNCTION_CALLING = 5


def _tool_declarations(non_blocking: bool = False) -> types.Tool:
    """`non_blocking=True` agrega `behavior=NON_BLOCKING` a `buscar_web` y
    `open_app`, para la sesión Live (`BidiGenerateContent`) de
    `VoiceEngine`. El agente de texto (`generate_content` normal) usa el
    default `False`: la API responde `400 INVALID_ARGUMENT
    ("FunctionDeclaration.behavior is only supported by the
    BidiGenerateContent method")` si el campo va en esa request —
    confirmado empíricamente (Fase 12), contra lo que asumía el plan
    original. Ver `plans/ERRORES.md`."""
    behavior = {"behavior": types.Behavior.NON_BLOCKING} if non_blocking else {}
    return types.Tool(function_declarations=[
        types.FunctionDeclaration(
            name="tareas",
            description="Gestiona las tareas pendientes del usuario: listar, crear, editar, completar o eliminar.",
            parameters_json_schema=_TAREAS_SCHEMA,
        ),
        types.FunctionDeclaration(
            name="recordatorios",
            description="Gestiona recordatorios y alarmas del usuario: listar, crear o eliminar.",
            parameters_json_schema=_RECORDATORIOS_SCHEMA,
        ),
        types.FunctionDeclaration(
            name="open_app",
            description="Abre una aplicación de escritorio por su nombre (ej. calculadora, chrome, spotify).",
            parameters_json_schema=_OPEN_APP_SCHEMA,
            **behavior,
        ),
        types.FunctionDeclaration(
            name="musica",
            description="Controla la reproducción de música: reproducir una canción por nombre, pausar, "
                        "siguiente, anterior, subir o bajar el volumen.",
            parameters_json_schema=_MUSICA_SCHEMA,
        ),
        types.FunctionDeclaration(
            name="buscar_web",
            description="Busca información real y actual en internet (noticias, precios, clima, hechos "
                        "recientes, recomendaciones) y devuelve un resumen de lo encontrado. Usar siempre "
                        "que la respuesta dependa de información que pueda haber cambiado recientemente.",
            parameters_json_schema=_BUSCAR_WEB_SCHEMA,
            **behavior,
        ),
    ])


class GeminiAgent:
    # "gemini-2.5-flash" sigue LISTADO por client.models.list() pero responde
    # 404 "no longer available to new users" con la API key real del usuario
    # (probado, Fase 05) — "gemini-flash-latest" es el alias vigente que sí
    # responde y sigue apuntando al flash recomendado cuando Google renombre
    # el modelo de nuevo.
    def __init__(self, api_key: str, model: str = "gemini-flash-latest"):
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self._tools_texto = _tool_declarations()
        self._tools_voz = _tool_declarations(non_blocking=True)
        self._stats = {"local": 0, "gemini": 0}

    def stats(self) -> dict:
        return dict(self._stats)

    @property
    def tools(self) -> types.Tool:
        """Declaraciones de tools para la sesión Live, reutilizadas por
        `VoiceEngine` para no duplicar el schema de function-calling —
        incluye `behavior=NON_BLOCKING` en `buscar_web`/`open_app` (Fase
        12). El agente de texto usa `_tools_texto` (sin ese campo) para su
        propia request, ver `_tool_declarations`."""
        return self._tools_voz

    def ejecutar_tool_directa(self, nombre: str, parametros: dict, player=None) -> str:
        """Ejecuta una tool ya decidida por otro motor de function-calling
        (ej. una sesión Live), reutilizando el mismo dispatch que `procesar`."""
        return self._ejecutar_tool(nombre, parametros, player)

    def procesar(self, texto: str, player=None) -> str:
        """Resuelve `texto` por matcher local; si no matchea, escala a Gemini."""
        texto = (texto or "").strip()
        if not texto:
            return "No escuché nada, señor."

        match = match_local(texto)
        if match:
            self._stats["local"] += 1
            return self._ejecutar_tool(match["tool"], match["parameters"], player)

        self._stats["gemini"] += 1
        return self._resolver_con_gemini(texto, player)

    def _resolver_con_gemini(self, texto: str, player=None) -> str:
        contents = [types.Content(role="user", parts=[types.Part(text=texto)])]
        config = types.GenerateContentConfig(tools=[self._tools_texto])

        for _ in range(_MAX_TURNOS_FUNCTION_CALLING):
            response = self.client.models.generate_content(
                model=self.model, contents=contents, config=config,
            )
            candidato = response.candidates[0] if response.candidates else None
            partes = candidato.content.parts if candidato and candidato.content else []
            llamadas = [p.function_call for p in partes if getattr(p, "function_call", None)]

            if not llamadas:
                return (getattr(response, "text", "") or "").strip() or "No tengo una respuesta, señor."

            contents.append(candidato.content)
            respuestas = []
            for fc in llamadas:
                argumentos = dict(fc.args or {})
                resultado = self._ejecutar_tool(fc.name, argumentos, player)
                respuestas.append(types.Part.from_function_response(
                    name=fc.name, response={"result": resultado},
                ))
            contents.append(types.Content(role="user", parts=respuestas))

        return "No pude completar la solicitud, señor (demasiados pasos)."

    def _ejecutar_tool(self, nombre: str, parametros: dict, player=None) -> str:
        if nombre == "buscar_web":
            return self._buscar_web(parametros, player)
        fn = _DISPATCH.get(nombre)
        if not fn:
            return f"Herramienta '{nombre}' no reconocida."
        try:
            return fn(parametros, player=player)
        except Exception as e:
            return f"Error ejecutando '{nombre}': {e}"

    def _buscar_web(self, parameters: dict, player=None) -> str:
        """Búsqueda real con grounding: request separada, solo con la tool
        `google_search` (mezclarla con `function_declarations` en la misma
        request es rechazado por la API)."""
        query = str(parameters.get("query", "")).strip()
        if not query:
            return "Necesito saber qué buscar, señor."

        config = types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())])
        try:
            response = self.client.models.generate_content(
                model=self.model, contents=query, config=config,
            )
        except Exception as e:
            return f"No pude buscar en la web: {e}"

        texto = (getattr(response, "text", "") or "").strip()
        if not texto:
            texto = "No encontré información relevante, señor."

        if bool(parameters.get("abrir_navegador", False)):
            try:
                import webbrowser
                webbrowser.open(f"https://www.google.com/search?q={quote(query)}")
            except Exception:
                pass

        if player and hasattr(player, "write_log"):
            try:
                player.write_log(f"Búsqueda web: {query}")
            except Exception:
                pass
        return texto
