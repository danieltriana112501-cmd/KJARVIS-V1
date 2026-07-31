"""recordatorios.py — Recordatorios y alarmas persistentes.

Se dispara en un momento exacto (fecha + hora) y hace que JARVIS avise al usuario
por voz local y con un sonido. Se soportan expresiones naturales como 'en 5 minutos',
'en 2 horas', 'mañana a las 10', 'el lunes a las 9', etc.

- RECORDATORIO (kind=reminder): al sonar, JARVIS solo avisa el mensaje.
- ALARMA (kind=alarm): al sonar, suena el tono y, si hay un `agente` (Fase 05,
  `GeminiAgent`) conectado vía `start_runner(..., agente=...)`, ejecuta
  `action_prompt` de verdad con `agente.procesar()` y lee la respuesta; sin
  agente, solo lee `action_prompt` en voz (comportamiento previo, fallback).

El almacenamiento está SEPARADO por tipo, dentro de la carpeta `datos/`:
  - `datos/recordatorios.json`  -> recordatorios
  - `datos/alarmas.json`        -> alarmas

Sobreviven a los reinicios: un runner en segundo plano los revisa cada pocos seg.

Adaptado de JARVIS-HRZ `_internal/actions/recordatorios.py` (Fase 03 del plan).
A diferencia del original, `_disparar()` NO llama a ningún LLM (ahorro de
cuota): avisa directo con una función de TTS local inyectada.
"""
import json
import re
import threading
import time
import uuid
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
REM_DIR = BASE_DIR / "datos"
REM_PATH = REM_DIR / "recordatorios.json"   # solo recordatorios (kind=reminder)
ALARM_PATH = REM_DIR / "alarmas.json"       # solo alarmas (kind=alarm)

_lock = threading.Lock()

_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_DIAS_NORM = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
_MESES_NORM = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
               "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _quitar_tildes(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


# ══════════════════════════════════════════════════════════════════════
#  Parseo de fecha/hora en lenguaje natural  ->  datetime
# ══════════════════════════════════════════════════════════════════════

def _parse_hora(texto: str, base_date):
    """Extrae una hora del texto ('a las 10', 'a las 3 de la tarde', '22:30').

    Devuelve (hour, minute) o None si no hay hora explícita.
    """
    t = texto
    pm = any(p in t for p in ("de la tarde", "de la noche", "pm", "p.m"))
    am = any(p in t for p in ("de la manana", "de la mañana", "am", "a.m", "de la madrugada"))

    m = re.search(r"(?:a\s+la[s]?\s+)?(\d{1,2})(?::(\d{2}))?\s*(?:h|hrs|horas)?", t)
    m2 = re.search(r"\bla[s]?\s+(\d{1,2})(?::(\d{2}))?", t)
    if m2:
        m = m2
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2)) if m.group(2) else 0
    if hour > 23 or minute > 59:
        return None
    if pm and hour < 12:
        hour += 12
    if am and hour == 12:
        hour = 0
    return (hour, minute)


def _resolver_fecha_base(t: str):
    """Resuelve la parte de FECHA del texto a un objeto date. Devuelve (date, encontrada)."""
    hoy = datetime.now().date()

    if "pasado manana" in t:
        return (hoy + timedelta(days=2), True)
    if "manana" in t:
        return (hoy + timedelta(days=1), True)
    if "hoy" in t or "esta noche" in t or "esta tarde" in t:
        return (hoy, True)

    m = re.search(r"(\d{1,2})\s+(?:de\s+)?([a-z]+)(?:\s+(?:de\s+)?(\d{4}))?", t)
    if m and m.group(2) in _MESES_NORM:
        dia = int(m.group(1))
        idx = _MESES_NORM.index(m.group(2)) + 1
        anio = int(m.group(3)) if m.group(3) else hoy.year
        try:
            cand = datetime(anio, idx, dia).date()
            if not m.group(3) and cand < hoy:
                cand = datetime(anio + 1, idx, dia).date()
            return (cand, True)
        except ValueError:
            pass

    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", t)
    if m:
        try:
            return (datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date(), True)
        except ValueError:
            pass

    for idx, dia in enumerate(_DIAS_NORM):
        if re.search(rf"\b{dia}\b", t):
            delta = (idx - hoy.weekday()) % 7
            if delta == 0:
                delta = 7
            return (hoy + timedelta(days=delta), True)

    return (hoy, False)


def resolver_datetime(texto: str, hora_param: str = "") -> datetime | None:
    """Convierte una expresión natural a un datetime concreto.

    Soporta: 'en N segundos/minutos/horas', 'en 1 hora y 30 minutos',
    'mañana a las 10', 'hoy a las 22:00', 'a las 15:30', 'el lunes a las 9',
    '11 de julio a las 8', ISO. `hora_param` es una hora HH:MM opcional aparte.
    Devuelve None si no logra interpretarlo.
    """
    if not texto and not hora_param:
        return None
    t = _quitar_tildes((texto or "").strip().lower())
    ahora = datetime.now()

    t = t.replace("media hora", "30 minutos").replace("medio hora", "30 minutos")
    t = t.replace("un cuarto de hora", "15 minutos").replace("cuarto de hora", "15 minutos")
    t = t.replace("hora y media", "90 minutos")

    _palabras_num = {
        "un": "1", "una": "1", "uno": "1", "dos": "2", "tres": "3", "cuatro": "4",
        "cinco": "5", "seis": "6", "siete": "7", "ocho": "8", "nueve": "9",
        "diez": "10", "once": "11", "doce": "12", "quince": "15", "veinte": "20",
        "treinta": "30",
    }
    _t_tokens = t.split()
    t = " ".join(_palabras_num.get(w, w) for w in _t_tokens)

    if t.startswith("en ") or "dentro de" in t:
        total = timedelta()
        encontrado = False
        for val, unit in re.findall(r"(\d+)\s*(segundo|seg|minuto|min|hora|hr|dia|semana)", t):
            n = int(val)
            encontrado = True
            if unit.startswith("seg"):
                total += timedelta(seconds=n)
            elif unit.startswith("min"):
                total += timedelta(minutes=n)
            elif unit.startswith("h"):
                total += timedelta(hours=n)
            elif unit.startswith("dia"):
                total += timedelta(days=n)
            elif unit.startswith("semana"):
                total += timedelta(weeks=n)
        if encontrado:
            return ahora + total

    fecha, fecha_encontrada = _resolver_fecha_base(t)

    hm = None
    if hora_param and re.fullmatch(r"\d{1,2}:\d{2}", hora_param.strip()):
        h, mi = hora_param.strip().split(":")
        hm = (int(h), int(mi))
    if hm is None:
        hm = _parse_hora(t, fecha)

    if hm is None:
        if not fecha_encontrada:
            return None
        hm = (9, 0)

    dt = datetime(fecha.year, fecha.month, fecha.day, hm[0], hm[1], 0)

    if not fecha_encontrada and dt <= ahora:
        dt += timedelta(days=1)

    return dt


# ══════════════════════════════════════════════════════════════════════
#  Persistencia
# ══════════════════════════════════════════════════════════════════════

def _read_file(path: Path) -> list:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write_file(path: Path, items: list) -> None:
    try:
        REM_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(items, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        print(f"[Recordatorios] Error al guardar {path.name}: {e}")


def _load() -> list:
    """Carga TODOS los elementos (recordatorios + alarmas) unificados."""
    with _lock:
        return _read_file(REM_PATH) + _read_file(ALARM_PATH)


def _save(items: list) -> None:
    """Guarda separando por tipo: recordatorios en un archivo, alarmas en otro."""
    with _lock:
        recordatorios_l = [r for r in items if r.get("kind") != "alarm"]
        alarmas_l = [r for r in items if r.get("kind") == "alarm"]
        _write_file(REM_PATH, recordatorios_l)
        _write_file(ALARM_PATH, alarmas_l)


def _ordenar(items: list) -> list:
    """Ordena por momento de disparo (más próximo primero); disparados al final."""
    def clave(r):
        return (bool(r.get("fired")), r.get("trigger_at", "") or "9999")
    return sorted(items, key=clave)


# ══════════════════════════════════════════════════════════════════════
#  Formateo legible
# ══════════════════════════════════════════════════════════════════════

def _formatear_hora_12h(dt: datetime) -> str:
    h = dt.hour
    sufijo = "am" if h < 12 else "pm"
    h12 = h % 12
    if h12 == 0:
        h12 = 12
    if dt.minute == 0:
        return f"{h12} {sufijo}"
    return f"{h12}:{dt.minute:02d} {sufijo}"


def _etiqueta_cuando(dt: datetime) -> str:
    """Ej: 'hoy a las 9 pm', 'mañana a las 10 am', 'el sábado 11 de julio a las 8 am'."""
    hoy = datetime.now().date()
    delta = (dt.date() - hoy).days
    hora_txt = f"a las {_formatear_hora_12h(dt)}"
    if delta == 0:
        return f"hoy {hora_txt}"
    if delta == 1:
        return f"mañana {hora_txt}"
    dia_sem = _DIAS[dt.weekday()]
    fecha_exacta = f"{dt.day} de {_MESES[dt.month - 1]}"
    if 2 <= delta <= 7:
        return f"el próximo {dia_sem} {fecha_exacta} {hora_txt}"
    return f"el {dia_sem} {fecha_exacta} {hora_txt}"


def _resumen(r: dict) -> str:
    msg = r.get("message", "(sin descripción)")
    try:
        dt = datetime.fromisoformat(r.get("trigger_at", ""))
        cuando = _etiqueta_cuando(dt)
    except Exception:
        cuando = ""
    tipo = "alarma" if r.get("kind") == "alarm" else "recordatorio"
    rec = ""
    recur = r.get("recurrence")
    if recur == "daily":
        rec = " (cada día)"
    elif recur == "weekly":
        rec = " (cada semana)"
    elif recur == "weekdays":
        dias = r.get("weekdays") or []
        nombres = [_DIAS[d] for d in sorted(set(dias)) if 0 <= d <= 6]
        if nombres:
            rec = " (cada " + ", ".join(nombres) + ")"
    if cuando:
        return f"{tipo}: '{msg}' — {cuando}{rec}"
    return f"{tipo}: '{msg}'{rec}"


# ══════════════════════════════════════════════════════════════════════
#  CRUD
# ══════════════════════════════════════════════════════════════════════

def _norm_weekdays(weekdays) -> list:
    """Normaliza la lista de días (0=lunes..6=domingo), únicos y ordenados."""
    if not weekdays:
        return []
    try:
        return sorted(set(int(d) for d in weekdays if 0 <= int(d) <= 6))
    except Exception:
        return []


def _parse_weekdays_texto(texto: str) -> list:
    """Convierte nombres de días en español a índices (0=lunes..6=domingo)."""
    t = _quitar_tildes((texto or "").lower())
    if not t:
        return []
    if "entre semana" in t or "dias laborales" in t or "laborables" in t:
        return [0, 1, 2, 3, 4]
    if "fin de semana" in t or "finde" in t:
        return [5, 6]
    if "todos los dias" in t or "diario" in t or "cada dia" in t:
        return [0, 1, 2, 3, 4, 5, 6]
    dias = []
    for idx, nombre in enumerate(_DIAS_NORM):
        if nombre in t or nombre[:3] in t:
            dias.append(idx)
    return sorted(set(dias))


def crear_recordatorio(message: str, when: str = "", time_param: str = "",
                       kind: str = "reminder", recurrence: str = "none",
                       action_prompt: str = "", weekdays=None,
                       trigger_at_iso: str = "") -> dict | None:
    """Crea y persiste un recordatorio/alarma. Devuelve el objeto o None si la fecha es inválida.

    - reminder: al sonar, JARVIS anuncia `message`.
    - alarm: al sonar, suena el tono y JARVIS lee `action_prompt` en voz.

    recurrence: none | daily | weekly | weekdays. Si es 'weekdays', `weekdays` es
    una lista de enteros 0=lunes .. 6=domingo con los días a repetir.
    """
    if trigger_at_iso:
        try:
            dt = datetime.fromisoformat(trigger_at_iso)
        except Exception:
            return None
    else:
        dt = resolver_datetime(when or "", time_param or "")
    if dt is None:
        return None
    wd = _norm_weekdays(weekdays)
    rec = recurrence if recurrence in ("daily", "weekly", "weekdays") else "none"
    if rec == "weekdays" and not wd:
        rec = "none"
    item = {
        "id": uuid.uuid4().hex[:12],
        "message": (message or "").strip(),
        "trigger_at": dt.replace(microsecond=0).isoformat(),
        "kind": "alarm" if str(kind).lower() == "alarm" else "reminder",
        "recurrence": rec,
        "weekdays": wd,
        "action_prompt": (action_prompt or "").strip(),
        "enabled": True,
        "fired": False,
        "created_at": datetime.now().isoformat(),
    }
    items = _load()
    items.append(item)
    _save(items)
    return item


def eliminar_recordatorio(rem_id: str) -> dict | None:
    items = _load()
    eliminado = None
    nuevos = []
    for r in items:
        if r.get("id") == rem_id and eliminado is None:
            eliminado = r
            continue
        nuevos.append(r)
    if eliminado:
        _save(nuevos)
    return eliminado


def listar_pendientes() -> list:
    return _ordenar([r for r in _load()
                     if r.get("kind", "reminder") != "alarm" and not r.get("fired")])


def listar_todo() -> list:
    """Recordatorios pendientes + alarmas (activas y desactivadas)."""
    items = _load()
    return _ordenar([r for r in items
                     if r.get("kind") == "alarm" or not r.get("fired")])


# ══════════════════════════════════════════════════════════════════════
#  Herramienta (para el matcher local / el agente de Gemini en la Fase 05)
# ══════════════════════════════════════════════════════════════════════

def recordatorios(parameters: dict, player=None) -> str:
    """Gestiona recordatorios y alarmas. Acciones: list | add | delete."""
    action = str(parameters.get("action", "")).lower().strip()

    if action in ("list", "read", "leer", "listar"):
        pend = listar_todo()
        if not pend:
            return "No tienes recordatorios ni alarmas pendientes, señor."
        lineas = [f"Tienes {len(pend)} recordatorio(s) pendiente(s):"]
        for i, r in enumerate(pend, 1):
            lineas.append(f"{i}. {_resumen(r)}")
        return "\n".join(lineas)

    if action in ("add", "create", "crear", "nuevo", "agregar", "set"):
        message = str(parameters.get("message", "") or parameters.get("description", "")).strip()
        when = str(parameters.get("when", "") or parameters.get("date", "")).strip()
        time_param = str(parameters.get("time", "")).strip()
        kind = str(parameters.get("kind", "reminder")).strip().lower()
        recurrence = str(parameters.get("recurrence", "none")).strip().lower()
        action_prompt = str(parameters.get("action_prompt", "")).strip()
        weekdays = parameters.get("weekdays", None)
        if isinstance(weekdays, str):
            weekdays = _parse_weekdays_texto(weekdays)
        elif isinstance(weekdays, list) and weekdays and isinstance(weekdays[0], str):
            weekdays = _parse_weekdays_texto(",".join(weekdays))
        if kind == "alarm" and not action_prompt and message:
            action_prompt = message
        if not message and action_prompt:
            message = action_prompt
        if kind == "alarm" and not message:
            message = "alarma"
        if not message:
            return "¿Qué quieres que te recuerde, señor?"
        if not when and not time_param:
            return "¿Para cuándo lo programo, señor? (ej: en 5 minutos, mañana a las 10)"
        item = crear_recordatorio(message, when, time_param, kind, recurrence, action_prompt, weekdays)
        if item is None:
            return ("No pude entender la fecha u hora, señor. "
                    "Prueba con algo como 'en 10 minutos', 'hoy a las 9 de la noche' o 'mañana a las 8'.")
        cuando = _etiqueta_cuando(datetime.fromisoformat(item["trigger_at"]))
        tipo = "Alarma" if item["kind"] == "alarm" else "Recordatorio"
        if player:
            try:
                player.write_log(f"[{tipo}] creado: {message} — {cuando}")
            except Exception:
                pass
        return f"{tipo} programado: '{message}', {cuando}."

    if action in ("delete", "eliminar", "borrar", "remove", "cancel", "cancelar"):
        rem_id = str(parameters.get("id", "") or parameters.get("task_id", "")).strip()
        busca = str(parameters.get("message", "")).strip().lower()
        items = _load()
        if not rem_id and busca:
            for r in items:
                if busca in r.get("message", "").lower():
                    rem_id = r.get("id")
                    break
        if not rem_id:
            return "No encontré ese recordatorio para eliminar, señor."
        elim = eliminar_recordatorio(rem_id)
        if not elim:
            return "No encontré ese recordatorio, señor."
        if player:
            try:
                player.write_log(f"Recordatorio eliminado: {elim.get('message')}")
            except Exception:
                pass
        return f"Recordatorio eliminado: '{elim.get('message')}'."

    return f"Acción de recordatorios '{action}' no soportada."


# ══════════════════════════════════════════════════════════════════════
#  Runner en segundo plano
# ══════════════════════════════════════════════════════════════════════

_runner_started = False


def _reproducir_tono(alarma: bool = False):
    """Reproduce el tono de aviso de JARVIS, audible SIEMPRE (activo o inactivo).

    Usa winsound.Beep (Windows-only, ya aceptado en el proyecto). Las alarmas
    suenan bastante más tiempo que los recordatorios para llamar la atención.
    """
    import winsound
    try:
        if alarma:
            patron = (880, 1047, 1319, 1047, 880, 1047, 1319, 1568)
            for _ in range(8):
                for freq in patron:
                    winsound.Beep(freq, 150)
                time.sleep(0.2)
        else:
            for freq in (988, 1319, 988, 1319):
                winsound.Beep(freq, 200)
    except Exception:
        try:
            winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS)
        except Exception:
            pass


def _disparar(item: dict, tts_fn, player=None, agente=None):
    """Dispara un recordatorio o alarma que venció.

    Recordatorios y alarmas sin `action_prompt` NO llaman a ningún LLM (ahorro
    de cuota): el aviso se lee tal cual con `tts_fn`. Solo una alarma con
    `action_prompt` y un `agente` (Fase 05, `GeminiAgent`) conectado ejecuta
    ese prompt de verdad antes de hablar la respuesta.
    """
    msg = item.get("message", "")
    es_alarma = item.get("kind") == "alarm"
    action_prompt = (item.get("action_prompt") or "").strip()

    threading.Thread(target=_reproducir_tono, args=(es_alarma,), daemon=True).start()

    if player:
        try:
            etiqueta = "ALARMA" if es_alarma else "RECORDATORIO"
            player.write_log(f"[{etiqueta}] {msg}")
        except Exception:
            pass

    texto = action_prompt if (es_alarma and action_prompt) else msg
    if es_alarma and action_prompt and agente is not None:
        try:
            respuesta = agente.procesar(action_prompt, player=player)
            if respuesta:
                texto = respuesta
        except Exception as e:
            print(f"[Recordatorios] Error ejecutando action_prompt vía agente: {e}")

    if tts_fn:
        try:
            tts_fn(texto)
        except Exception as e:
            print(f"[Recordatorios] Error en tts_fn: {e}")


def _siguiente_disparo(item: dict, dt: datetime):
    """Calcula el próximo disparo según la recurrencia. None = no se repite."""
    rec = item.get("recurrence", "none")
    if rec == "daily":
        return dt + timedelta(days=1)
    if rec == "weekly":
        return dt + timedelta(weeks=1)
    if rec == "weekdays":
        dias = item.get("weekdays") or []
        dias = sorted(set(int(d) for d in dias if 0 <= int(d) <= 6))
        if not dias:
            return None
        for i in range(1, 8):
            cand = dt + timedelta(days=i)
            if cand.weekday() in dias:
                return cand
        return None
    return None


def _loop_runner(tts_fn, player, agente=None):
    """Revisa periódicamente los recordatorios y dispara los que vencen."""
    while True:
        try:
            ahora = datetime.now()
            items = _load()
            cambiado = False
            for item in items:
                if item.get("fired"):
                    continue
                if item.get("enabled") is False:
                    continue
                try:
                    dt = datetime.fromisoformat(item.get("trigger_at", ""))
                except Exception:
                    continue
                if dt <= ahora:
                    print(f"[Recordatorios] DISPARANDO {item.get('kind')} '{item.get('message')}' "
                          f"(id={item.get('id')}) programado para {item.get('trigger_at')}")
                    _disparar(item, tts_fn, player, agente)
                    proximo = _siguiente_disparo(item, dt)
                    if proximo is not None:
                        item["trigger_at"] = proximo.replace(microsecond=0).isoformat()
                    else:
                        item["fired"] = True
                        item["enabled"] = False
                    cambiado = True
                    time.sleep(2)
            if cambiado:
                _save(items)
        except Exception as e:
            print(f"[Recordatorios] Error en runner: {e}")
        time.sleep(10)


def start_runner(tts_fn, player=None, agente=None) -> None:
    """Inicia el hilo que dispara los recordatorios. Idempotente.

    `agente` es opcional (Fase 05, `GeminiAgent`): si se pasa, las alarmas
    con `action_prompt` lo ejecutan de verdad en vez de solo leerlo en voz.
    """
    global _runner_started
    if _runner_started:
        return
    _runner_started = True
    threading.Thread(
        target=_loop_runner,
        args=(tts_fn, player, agente),
        daemon=True,
    ).start()
    print("[JARVIS] Runner de recordatorios iniciado.")
