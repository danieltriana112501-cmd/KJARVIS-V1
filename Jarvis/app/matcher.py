"""matcher.py — Resolución local de acciones por regex/keywords (sin IA).

Ahorra cuota de Gemini: toda acción determinista (agregar/listar/completar
tarea, etc.) se intenta acá primero. Si ninguna regla matchea, el llamador
debe escalar a Gemini (esa integración la hace la Fase 05).
"""
import re
import unicodedata

from app.actions.open_app import _normalize as _normalizar_app, _VERB_PREFIX as _APP_VERB_PREFIX

_TRAILING_FLUFF = re.compile(
    r"[\s,]*(por favor|please|gracias|thanks|jarvis)[\s\.\!\?,]*$",
    re.IGNORECASE,
)

_LEADING_JARVIS = re.compile(r"^(jarvis)[\s,]+", re.IGNORECASE)


def _quitar_tildes(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


def _limpiar(texto: str) -> str:
    """Quita coletillas ('jarvis', 'por favor', 'gracias') y puntuación final."""
    t = (texto or "").strip()
    prev = None
    while prev != t:
        prev = t
        t = _TRAILING_FLUFF.sub("", t).strip()
    t = _LEADING_JARVIS.sub("", t).strip()
    t = re.sub(r"[\?\!\.]+$", "", t).strip()
    t = re.sub(r"\s+", " ", t)
    return t


_DATE_PATTERN = re.compile(
    r"\b("
    r"pasado\s+ma[ñn]ana|ma[ñn]ana|hoy|"
    r"el\s+pr[oó]ximo\s+\w+|"
    r"(?:el\s+)?(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)|"
    r"\d{1,2}\s+de\s+\w+(?:\s+de\s+\d{4})?|"
    r"\d{1,2}[/\-]\d{1,2}(?:[/\-]\d{2,4})?|"
    r"en\s+\d+\s+d[ií]as?|en\s+\d+\s+semanas?"
    r")\b",
    re.IGNORECASE,
)


def _extraer_fecha(texto: str) -> tuple:
    """Separa una frase de fecha de la descripción.

    Se asume que la fecha suele ir al final ('comprar pan mañana'); si hay
    más de una coincidencia se toma la última.
    """
    matches = list(_DATE_PATTERN.finditer(texto))
    if not matches:
        return texto.strip(" ,"), ""
    m = matches[-1]
    fecha = m.group(0).strip()
    descripcion = (texto[:m.start()] + texto[m.end():]).strip(" ,")
    descripcion = re.sub(r"\s+", " ", descripcion)
    return descripcion, fecha


_ADD_PATTERNS = [
    re.compile(
        r"^(?:agrega(?:me)?|agregar|a[ñn]ade|a[ñn]adir|pon|anota(?:me)?|crea(?:r)?)\s+"
        r"(?:una\s+)?tarea\s+(?:de\s+|que\s+)?(.+)$",
        re.IGNORECASE,
    ),
    re.compile(r"^nueva\s+tarea\s+(?:de\s+|que\s+)?(.+)$", re.IGNORECASE),
    re.compile(r"^recu[eé]rdame\s+que\s+(?:tengo\s+que\s+)?(.+)$", re.IGNORECASE),
]

_COMPLETE_PATTERNS = [
    re.compile(
        r"^(?:marca(?:r)?\s+como\s+(?:hecha|hecho|completada|completado)|"
        r"completa(?:r)?\s+la\s+tarea|ya\s+hice|termin[eé])\s+(?:de\s+)?(.+)$",
        re.IGNORECASE,
    ),
]

_DELETE_PATTERNS = [
    re.compile(
        r"^(?:elimina(?:r)?|borra(?:r)?|quita(?:r)?)\s+la\s+tarea\s+(?:de\s+)?(.+)$",
        re.IGNORECASE,
    ),
]

_LIST_PATTERNS = [
    re.compile(r"^(cuales son )?mis (tareas|pendientes)$"),
    re.compile(r"^que tareas tengo( pendientes)?$"),
    re.compile(r"^que tengo que hacer( hoy)?$"),
    re.compile(r"^lista de tareas$"),
]


def _match_tareas(texto_limpio: str) -> dict | None:
    normalizado = _quitar_tildes(texto_limpio.lower())

    for patron in _LIST_PATTERNS:
        if patron.match(normalizado):
            return {"tool": "tareas", "parameters": {"action": "list"}}

    for patron in _DELETE_PATTERNS:
        m = patron.match(texto_limpio)
        if m:
            descripcion = m.group(1).strip(" ,")
            if descripcion:
                return {"tool": "tareas", "parameters": {"action": "delete", "description": descripcion}}

    for patron in _COMPLETE_PATTERNS:
        m = patron.match(texto_limpio)
        if m:
            descripcion = m.group(1).strip(" ,")
            if descripcion:
                return {"tool": "tareas", "parameters": {"action": "complete", "description": descripcion}}

    for patron in _ADD_PATTERNS:
        m = patron.match(texto_limpio)
        if m:
            resto = m.group(1).strip(" ,")
            if not resto:
                continue
            descripcion, fecha = _extraer_fecha(resto)
            if not descripcion:
                continue
            parametros = {"action": "add", "description": descripcion}
            if fecha:
                parametros["date"] = fecha
            return {"tool": "tareas", "parameters": parametros}

    return None


_REM_LIST_PATTERNS = [
    re.compile(r"^(?:que |cuales son )?(?:mis )?(?:recordatorios|alarmas)(?:\s+tengo)?$"),
    re.compile(r"^lista de (?:recordatorios|alarmas)$"),
]

_REM_DELETE_PATTERNS = [
    re.compile(
        r"^(?:cancela(?:r)?|elimina(?:r)?|borra(?:r)?|quita(?:r)?)\s+"
        r"(?:el\s+|la\s+)?(recordatorio|alarma)\s+(?:de\s+)?(.+)$",
        re.IGNORECASE,
    ),
]

_ALARM_ADD_PATTERNS = [
    re.compile(r"^pon(?:me)?\s+una\s+alarma\s+(.+)$", re.IGNORECASE),
    re.compile(r"^despi[eé]rtame\s+(.+)$", re.IGNORECASE),
]

_REMINDER_ADD_PATTERNS = [
    re.compile(r"^recu[eé]rdame\s+(?:que\s+(?:tengo\s+que\s+)?)?(.+)$", re.IGNORECASE),
]

# Lo que la fase considera "hora explícita": dispara recordatorios en vez de
# tareas ("a las 5", "en 20 minutos") aunque el verbo sea el mismo ("recuérdame").
_HORA_EXPLICITA_PATTERN = re.compile(
    r"\b(?:a\s+la[s]?\s+\d{1,2}(?::\d{2})?|en\s+\d+\s+(?:segundo|seg|minuto|min|hora)s?)\b",
    re.IGNORECASE,
)

_CUANDO_TOKEN = re.compile(
    r"\b(?:pasado\s+ma[ñn]ana|ma[ñn]ana|hoy|"
    r"(?:el\s+)?(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)|"
    r"a\s+la[s]?\s+\d{1,2}(?::\d{2})?|"
    r"en\s+\d+\s+(?:segundo|seg|minuto|min|hora)s?"
    r")\b",
    re.IGNORECASE,
)


def _extraer_cuando(texto: str) -> tuple:
    """Separa la frase temporal (desde el primer token de tiempo hasta el final)."""
    matches = list(_CUANDO_TOKEN.finditer(texto))
    if not matches:
        return texto.strip(" ,"), ""
    inicio = matches[0].start()
    cuando = texto[inicio:].strip(" ,")
    mensaje = re.sub(r"\s+", " ", texto[:inicio]).strip(" ,")
    return mensaje, cuando


def _match_recordatorios(texto_limpio: str) -> dict | None:
    normalizado = _quitar_tildes(texto_limpio.lower())

    for patron in _REM_LIST_PATTERNS:
        if patron.match(normalizado):
            return {"tool": "recordatorios", "parameters": {"action": "list"}}

    for patron in _REM_DELETE_PATTERNS:
        m = patron.match(texto_limpio)
        if m:
            tipo, descripcion = m.group(1), m.group(2).strip(" ,")
            if descripcion:
                kind = "alarm" if "alarma" in tipo.lower() else "reminder"
                return {
                    "tool": "recordatorios",
                    "parameters": {"action": "delete", "message": descripcion, "kind": kind},
                }

    for patron in _ALARM_ADD_PATTERNS:
        m = patron.match(texto_limpio)
        if m:
            resto = re.sub(r"^(?:para|de)\s+", "", m.group(1).strip(" ,"), flags=re.IGNORECASE).strip()
            if not resto:
                continue
            return {"tool": "recordatorios", "parameters": {"action": "add", "kind": "alarm", "when": resto}}

    for patron in _REMINDER_ADD_PATTERNS:
        m = patron.match(texto_limpio)
        if m:
            resto = m.group(1).strip(" ,")
            if not resto or not _HORA_EXPLICITA_PATTERN.search(resto):
                continue
            mensaje, cuando = _extraer_cuando(resto)
            if not mensaje:
                continue
            return {
                "tool": "recordatorios",
                "parameters": {"action": "add", "kind": "reminder", "message": mensaje, "when": cuando},
            }

    return None


def _match_open_app(texto_limpio: str) -> dict | None:
    if not _APP_VERB_PREFIX.match(texto_limpio):
        return None
    app_name = _normalizar_app(texto_limpio)
    if not app_name:
        return None
    return {"tool": "open_app", "parameters": {"app_name": app_name}}


_MUSICA_PLAY_PATTERNS = [
    re.compile(
        r"^(?:pon(?:me)?|reproduce(?:r)?|toca(?:r)?)\s+"
        r"(?:la\s+canci[oó]n\s+|la\s+m[uú]sica\s+de\s+)?(.+)$",
        re.IGNORECASE,
    ),
]

_MUSICA_PAUSE_PATTERN = re.compile(r"^pausa(?:r)?(?:\s+la\s+m[uú]sica)?$", re.IGNORECASE)
_MUSICA_NEXT_PATTERNS = [
    re.compile(r"^siguiente\s+canci[oó]n$", re.IGNORECASE),
    re.compile(r"^salta(?:r)?\s+esta\s+canci[oó]n$", re.IGNORECASE),
]
_MUSICA_PREV_PATTERN = re.compile(r"^canci[oó]n\s+anterior$", re.IGNORECASE)
_MUSICA_VOLUME_UP_PATTERN = re.compile(r"^sube(?:r)?\s+el\s+volumen$", re.IGNORECASE)
_MUSICA_VOLUME_DOWN_PATTERN = re.compile(r"^baja(?:r)?\s+el\s+volumen$", re.IGNORECASE)


def _match_musica(texto_limpio: str) -> dict | None:
    if _MUSICA_PAUSE_PATTERN.match(texto_limpio):
        return {"tool": "musica", "parameters": {"action": "pause"}}
    for patron in _MUSICA_NEXT_PATTERNS:
        if patron.match(texto_limpio):
            return {"tool": "musica", "parameters": {"action": "next"}}
    if _MUSICA_PREV_PATTERN.match(texto_limpio):
        return {"tool": "musica", "parameters": {"action": "prev"}}
    if _MUSICA_VOLUME_UP_PATTERN.match(texto_limpio):
        return {"tool": "musica", "parameters": {"action": "volume", "value": "up"}}
    if _MUSICA_VOLUME_DOWN_PATTERN.match(texto_limpio):
        return {"tool": "musica", "parameters": {"action": "volume", "value": "down"}}
    for patron in _MUSICA_PLAY_PATTERNS:
        m = patron.match(texto_limpio)
        if m:
            query = m.group(1).strip(" ,")
            if query:
                return {"tool": "musica", "parameters": {"action": "play", "query": query}}
    return None


def match_local(texto: str) -> dict | None:
    """Intenta resolver `texto` con reglas locales (sin IA).

    Devuelve un dict {"tool": ..., "parameters": {...}} si matchea, o None
    si no matchea ningún patrón conocido (en ese caso el llamador debe
    escalar a Gemini — esa conexión la hace la Fase 05).
    """
    limpio = _limpiar(texto)
    if not limpio:
        return None
    resultado = _match_recordatorios(limpio)
    if resultado:
        return resultado
    resultado = _match_tareas(limpio)
    if resultado:
        return resultado
    resultado = _match_open_app(limpio)
    if resultado:
        return resultado
    return _match_musica(limpio)


def _check() -> None:
    assert match_local("agregar tarea comprar pan mañana") == {
        "tool": "tareas",
        "parameters": {"action": "add", "description": "comprar pan", "date": "mañana"},
    }
    assert match_local("nueva tarea llamar al dentista el lunes") == {
        "tool": "tareas",
        "parameters": {"action": "add", "description": "llamar al dentista", "date": "el lunes"},
    }
    assert match_local("recuérdame que tengo que pagar la luz hoy") == {
        "tool": "tareas",
        "parameters": {"action": "add", "description": "pagar la luz", "date": "hoy"},
    }
    assert match_local("marca como hecha comprar pan") == {
        "tool": "tareas",
        "parameters": {"action": "complete", "description": "comprar pan"},
    }
    assert match_local("qué tareas tengo") == {"tool": "tareas", "parameters": {"action": "list"}}
    assert match_local("mis pendientes") == {"tool": "tareas", "parameters": {"action": "list"}}
    assert match_local("elimina la tarea comprar pan") == {
        "tool": "tareas",
        "parameters": {"action": "delete", "description": "comprar pan"},
    }
    assert match_local("cuéntame un chiste") is None
    assert match_local("") is None

    assert match_local("qué recordatorios tengo") == {"tool": "recordatorios", "parameters": {"action": "list"}}
    assert match_local("mis alarmas") == {"tool": "recordatorios", "parameters": {"action": "list"}}
    assert match_local("recuérdame llamar al doctor a las 5") == {
        "tool": "recordatorios",
        "parameters": {"action": "add", "kind": "reminder", "message": "llamar al doctor", "when": "a las 5"},
    }
    assert match_local("pon una alarma para las 7") == {
        "tool": "recordatorios",
        "parameters": {"action": "add", "kind": "alarm", "when": "las 7"},
    }
    assert match_local("despiértame a las 6") == {
        "tool": "recordatorios",
        "parameters": {"action": "add", "kind": "alarm", "when": "a las 6"},
    }
    assert match_local("cancela el recordatorio de sacar la basura") == {
        "tool": "recordatorios",
        "parameters": {"action": "delete", "message": "sacar la basura", "kind": "reminder"},
    }
    assert match_local("borra la alarma de las 7") == {
        "tool": "recordatorios",
        "parameters": {"action": "delete", "message": "las 7", "kind": "alarm"},
    }
    # Ambiguo sin hora explícita: debe seguir resolviendo a tareas (regla de desambiguación).
    assert match_local("recuérdame que tengo que pagar la luz hoy") == {
        "tool": "tareas",
        "parameters": {"action": "add", "description": "pagar la luz", "date": "hoy"},
    }

    assert match_local("abre calculadora") == {
        "tool": "open_app",
        "parameters": {"app_name": "calculadora"},
    }
    assert match_local("abrime bloc de notas") == {
        "tool": "open_app",
        "parameters": {"app_name": "bloc de notas"},
    }
    assert match_local("ejecuta chrome") == {
        "tool": "open_app",
        "parameters": {"app_name": "chrome"},
    }

    assert match_local("pon bohemian rhapsody") == {
        "tool": "musica",
        "parameters": {"action": "play", "query": "bohemian rhapsody"},
    }
    assert match_local("reproduce bohemian rhapsody") == {
        "tool": "musica",
        "parameters": {"action": "play", "query": "bohemian rhapsody"},
    }
    assert match_local("pausa la música") == {"tool": "musica", "parameters": {"action": "pause"}}
    assert match_local("siguiente canción") == {"tool": "musica", "parameters": {"action": "next"}}
    assert match_local("salta esta canción") == {"tool": "musica", "parameters": {"action": "next"}}
    assert match_local("canción anterior") == {"tool": "musica", "parameters": {"action": "prev"}}
    assert match_local("sube el volumen") == {
        "tool": "musica",
        "parameters": {"action": "volume", "value": "up"},
    }
    assert match_local("baja el volumen") == {
        "tool": "musica",
        "parameters": {"action": "volume", "value": "down"},
    }

    print("OK")


if __name__ == "__main__":
    _check()
