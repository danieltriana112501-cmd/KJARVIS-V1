"""tareas.py — Gestor de tareas (tasks) con descripción, fecha y hora.

Las tareas se guardan en `Jarvis/datos/tareas.json`. Se pueden crear
manualmente desde la interfaz, por voz, o por la IA. Al leerlas se priorizan
las más próximas por fecha.

Adaptado de JARVIS-HRZ `_internal/actions/tareas.py` (Fase 02 del plan).
"""
import json
import re
import threading
import uuid
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
TAREAS_DIR = BASE_DIR / "datos"
TAREAS_PATH = TAREAS_DIR / "tareas.json"

_lock = threading.Lock()

_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

_DIAS_NORM = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]


def _quitar_tildes(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


_MESES_NORM = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
               "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _proximo_anio_para(mes: int, dia: int, hoy) -> int:
    anio = hoy.year
    try:
        candidata = datetime(anio, mes, dia).date()
        if candidata < hoy:
            anio += 1
    except ValueError:
        pass
    return anio


def _resolver_fecha(texto: str) -> str:
    """Convierte una fecha en lenguaje natural a 'YYYY-MM-DD' usando la fecha real del sistema.

    Acepta: '' (vacío), ISO 'YYYY-MM-DD', 'hoy', 'mañana', 'pasado mañana',
    'lunes'..'domingo' (próxima ocurrencia), 'en N dias', '11 de julio',
    '11 de julio de 2026', '11/07', '11/07/2026', '11-07-2026'.
    Si no logra interpretarlo, devuelve '' (evita fechas inválidas en la interfaz).
    """
    if not texto:
        return ""
    t = _quitar_tildes(texto.strip().lower())

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t):
        return t

    hoy = datetime.now().date()

    if t in ("hoy", "ahora", "today"):
        return hoy.isoformat()
    if t in ("manana", "tomorrow"):
        return (hoy + timedelta(days=1)).isoformat()
    if t in ("pasado manana", "pasadomanana"):
        return (hoy + timedelta(days=2)).isoformat()

    m = re.search(r"(?:en|dentro de)\s+(\d+)\s+dia", t)
    if m:
        return (hoy + timedelta(days=int(m.group(1)))).isoformat()

    m = re.search(r"(?:en|dentro de)\s+(\d+)\s+semana", t)
    if m:
        return (hoy + timedelta(weeks=int(m.group(1)))).isoformat()

    m = re.search(r"(\d{1,2})\s+(?:de\s+)?([a-z]+)(?:\s+(?:de\s+)?(\d{4}))?", t)
    if m:
        dia = int(m.group(1))
        nombre_mes = m.group(2)
        anio_txt = m.group(3)
        for idx, mes_nombre in enumerate(_MESES_NORM, start=1):
            if nombre_mes == mes_nombre:
                anio = int(anio_txt) if anio_txt else _proximo_anio_para(idx, dia, hoy)
                try:
                    return datetime(anio, idx, dia).date().isoformat()
                except ValueError:
                    return ""

    m = re.fullmatch(r"(\d{1,2})[/\-.](\d{1,2})(?:[/\-.](\d{2,4}))?", t)
    if m:
        dia = int(m.group(1))
        mes = int(m.group(2))
        anio_txt = m.group(3)
        if 1 <= mes <= 12 and 1 <= dia <= 31:
            if anio_txt:
                anio = int(anio_txt)
                if anio < 100:
                    anio += 2000
            else:
                anio = _proximo_anio_para(mes, dia, hoy)
            try:
                return datetime(anio, mes, dia).date().isoformat()
            except ValueError:
                return ""

    for idx, dia in enumerate(_DIAS_NORM):
        if dia in t:
            delta = (idx - hoy.weekday()) % 7
            if delta == 0:
                delta = 7
            return (hoy + timedelta(days=delta)).isoformat()

    return ""


def _load() -> list:
    with _lock:
        if not TAREAS_PATH.exists():
            return []
        try:
            data = json.loads(TAREAS_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []


def _save(tareas: list) -> None:
    with _lock:
        try:
            TAREAS_DIR.mkdir(parents=True, exist_ok=True)
            TAREAS_PATH.write_text(
                json.dumps(tareas, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"[Tareas] Error al guardar: {e}")


def _ordenar_recientes(tareas: list) -> list:
    return sorted(
        tareas,
        key=lambda t: t.get("created_at", ""),
        reverse=True,
    )


def _clave_fecha(t: dict) -> tuple:
    """Las tareas sin fecha van al final, ordenadas por creación reciente."""
    fecha = t.get("date", "")
    hora = t.get("time", "") or "99:99"
    if fecha:
        return (0, fecha, hora)
    return (1, t.get("created_at", ""), "")


def _ordenar_por_fecha(tareas: list) -> list:
    return sorted(tareas, key=_clave_fecha)


def _etiqueta_dia(fecha_dt) -> str:
    """Ej: 'hoy, 4 de julio', 'mañana, 5 de julio', 'el próximo sábado 11 de julio'."""
    hoy = datetime.now().date()
    d = fecha_dt.date()
    delta = (d - hoy).days
    dia_sem = _DIAS[fecha_dt.weekday()]
    fecha_exacta = f"{fecha_dt.day} de {_MESES[fecha_dt.month - 1]}"
    if delta == 0:
        return f"hoy, {fecha_exacta}"
    if delta == 1:
        return f"mañana, {fecha_exacta}"
    if delta == -1:
        return f"ayer, {fecha_exacta}"
    if 2 <= delta <= 7:
        return f"el próximo {dia_sem} {fecha_exacta}"
    return f"el {dia_sem} {fecha_exacta}"


def _formatear_hora_12h(hora: str) -> str:
    try:
        h = datetime.strptime(hora.strip(), "%H:%M")
        sufijo = "am" if h.hour < 12 else "pm"
        h12 = h.hour % 12
        if h12 == 0:
            h12 = 12
        if h.minute == 0:
            return f"{h12} {sufijo}"
        return f"{h12}:{h.minute:02d} {sufijo}"
    except Exception:
        return hora


def _formatear_fecha_hora(fecha: str, hora: str) -> str:
    partes = []
    if fecha:
        try:
            d = datetime.strptime(fecha, "%Y-%m-%d")
            partes.append(_etiqueta_dia(d))
        except Exception:
            partes.append(fecha)
    if hora:
        partes.append(f"a las {_formatear_hora_12h(hora)}")
    return " ".join(partes)


def _resumen_tarea(t: dict) -> str:
    desc = t.get("description", "(sin descripción)")
    cuando = _formatear_fecha_hora(t.get("date", ""), t.get("time", ""))
    estado = " [completada]" if t.get("done") else ""
    if cuando:
        return f"{desc} — {cuando}{estado}"
    return f"{desc}{estado}"


def listar_tareas() -> list:
    """Todas las tareas (pendientes y completadas), ordenadas por fecha próxima."""
    return _ordenar_por_fecha(_load())


def crear_tarea(description: str, date: str = "", time: str = "") -> dict:
    """La fecha es opcional y puede venir en lenguaje natural; se resuelve a 'YYYY-MM-DD'."""
    tareas = _load()
    tarea = {
        "id": uuid.uuid4().hex[:12],
        "description": description.strip(),
        "date": _resolver_fecha(date or ""),
        "time": (time or "").strip(),
        "done": False,
        "created_at": datetime.now().isoformat(),
    }
    tareas.append(tarea)
    _save(tareas)
    return tarea


def editar_tarea(task_id: str, description: str = None, date: str = None, time: str = None) -> dict:
    items = _load()
    encontrada = None
    for t in items:
        if t.get("id") == task_id:
            encontrada = t
            break
    if not encontrada:
        return None
    if description is not None and str(description).strip():
        encontrada["description"] = str(description).strip()
    if date is not None:
        encontrada["date"] = _resolver_fecha(str(date).strip())
    if time is not None:
        encontrada["time"] = str(time).strip()
    _save(items)
    return encontrada


def tareas(parameters: dict, player=None) -> str:
    """Gestiona las tareas del usuario.

    Acciones: list | add | edit | complete | delete
    Parámetros: action, description, date (YYYY-MM-DD o lenguaje natural), time (HH:MM), task_id
    `player` es opcional (lo usará la interfaz de la Fase 08 para loggear); no se
    depende de su existencia acá.
    """
    action = str(parameters.get("action", "list")).lower().strip()

    if action in ("list", "read", "leer", "listar"):
        items = _load()
        pendientes = [t for t in items if not t.get("done")]
        if not pendientes:
            return "No tienes tareas pendientes, señor."
        ordenadas = _ordenar_por_fecha(pendientes)
        lineas = [f"Tienes {len(ordenadas)} tarea(s) pendiente(s), de la más próxima a la más lejana:"]
        for i, t in enumerate(ordenadas, 1):
            lineas.append(f"{i}. {_resumen_tarea(t)}")
        return "\n".join(lineas)

    elif action in ("add", "create", "crear", "agregar", "nueva"):
        description = str(parameters.get("description", "")).strip()
        date_val = str(parameters.get("date", "")).strip()
        time_val = str(parameters.get("time", "")).strip()
        if not description:
            return "Necesito una descripción para crear la tarea, señor."
        if not date_val:
            return "Necesito una fecha para la tarea, señor. ¿Para qué día la programo?"
        tarea = crear_tarea(description, date_val, time_val)
        cuando = _formatear_fecha_hora(tarea.get("date", ""), tarea.get("time", ""))
        if player:
            try:
                player.write_log(f"Tarea creada: {description}")
            except Exception:
                pass
        if cuando:
            return f"Tarea creada: '{description}', {cuando}."
        return f"Tarea creada: '{description}'."

    elif action in ("edit", "editar", "update", "actualizar", "modificar"):
        task_id = str(parameters.get("task_id", "")).strip()
        desc_busqueda = str(parameters.get("description", "")).strip()
        items = _load()
        encontrada = None
        for t in items:
            if task_id and t.get("id") == task_id:
                encontrada = t
                break
        if not encontrada and not task_id and desc_busqueda:
            for t in items:
                if desc_busqueda.lower() in t.get("description", "").lower():
                    encontrada = t
                    break
        if not encontrada:
            return "No encontré esa tarea para editar, señor."
        nueva_desc = parameters.get("new_description", None)
        if nueva_desc is None:
            nueva_desc = parameters.get("description", None) if task_id else None
        if nueva_desc is not None and str(nueva_desc).strip():
            encontrada["description"] = str(nueva_desc).strip()
        if "date" in parameters and str(parameters.get("date", "")).strip():
            encontrada["date"] = _resolver_fecha(str(parameters.get("date")).strip())
        if "time" in parameters:
            encontrada["time"] = str(parameters.get("time", "")).strip()
        _save(items)
        cuando = _formatear_fecha_hora(encontrada.get("date", ""), encontrada.get("time", ""))
        if cuando:
            return f"Tarea actualizada: '{encontrada.get('description')}', {cuando}."
        return f"Tarea actualizada: '{encontrada.get('description')}'."

    elif action in ("complete", "completar", "done", "hecho", "mark_done"):
        task_id = str(parameters.get("task_id", "")).strip()
        desc = str(parameters.get("description", "")).strip().lower()
        items = _load()
        encontrada = None
        for t in items:
            if task_id and t.get("id") == task_id:
                encontrada = t
                break
            if desc and desc in t.get("description", "").lower():
                encontrada = t
                break
        if not encontrada:
            return "No encontré esa tarea, señor."
        encontrada["done"] = True
        _save(items)
        return f"Tarea completada: '{encontrada.get('description')}'."

    elif action in ("delete", "eliminar", "borrar", "remove"):
        task_id = str(parameters.get("task_id", "")).strip()
        desc = str(parameters.get("description", "")).strip().lower()
        items = _load()
        nuevas = []
        eliminada = None
        for t in items:
            if (task_id and t.get("id") == task_id) or (
                desc and desc in t.get("description", "").lower() and eliminada is None
            ):
                eliminada = t
                continue
            nuevas.append(t)
        if not eliminada:
            return "No encontré esa tarea para eliminar, señor."
        _save(nuevas)
        return f"Tarea eliminada: '{eliminada.get('description')}'."

    return f"Acción de tareas '{action}' no soportada."
