"""_check_tools_async.py — Self-check automatizable de la Fase 12 (tools
NON_BLOCKING + caché del Menú Inicio).

No requiere red ni API key: solo valida la declaración de tools y la caché
de `open_app.py`. Los puntos 4-6 de la Verificación de la fase (frases de
relleno, scheduling real con la Live API, no-regresión en vivo de
tareas/recordatorios/musica) requieren un humano hablando por voz — ver
plans/phase-12-tools-async.md.
"""
import asyncio
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from google.genai import types

from app.gemini_agent import _tool_declarations
from app.voice_engine import VoiceEngine, _TOOLS_NO_BLOQUEANTES
import app.actions.open_app as open_app_mod


class _AgenteFalso:
    """Standin de GeminiAgent — no pega a la red, solo confirma el
    despacho de VoiceEngine hacia `ejecutar_tool_directa`."""

    def ejecutar_tool_directa(self, nombre, parametros, player=None):
        return f"resultado-{nombre}"


class _SesionFalsa:
    def __init__(self):
        self.enviados: list = []

    async def send_tool_response(self, function_responses):
        self.enviados.append(function_responses)


async def _check_dispatch_no_bloqueante() -> None:
    """Ejercita `_lanzar_tool_no_bloqueante` de punta a punta (sin Live API
    real): confirma que la task queda referenciada mientras corre (para no
    perderla al GC), que se saca de la lista al terminar, y que la
    FunctionResponse manda el `scheduling` correcto por tool."""
    motor = VoiceEngine(api_key="x", voice="Kore", agente=_AgenteFalso())
    sesion = _SesionFalsa()
    loop = asyncio.get_running_loop()
    fc = SimpleNamespace(id="call-1", name="buscar_web", args={"query": "clima"})

    motor._lanzar_tool_no_bloqueante(sesion, loop, fc)
    assert len(motor._tools_pendientes) == 1, "la task no quedó referenciada (riesgo de GC a mitad de camino)"
    await asyncio.gather(*motor._tools_pendientes)
    await asyncio.sleep(0)  # deja correr el done_callback que la saca de la lista

    assert motor._tools_pendientes == [], "la task no se removió de _tools_pendientes al terminar"
    assert len(sesion.enviados) == 1, sesion.enviados
    respuesta = sesion.enviados[0][0]
    assert respuesta.id == "call-1" and respuesta.name == "buscar_web"
    assert respuesta.scheduling == _TOOLS_NO_BLOQUEANTES["buscar_web"], respuesta.scheduling
    assert respuesta.response == {"result": "resultado-buscar_web"}, respuesta.response


def _check() -> None:
    print("[1/4] types.FunctionDeclaration acepta behavior=NON_BLOCKING...")
    types.FunctionDeclaration(name="x", behavior=types.Behavior.NON_BLOCKING)
    print("  -> OK")

    print("[2/4] variante de voz (non_blocking=True): buscar_web/open_app NON_BLOCKING, resto BLOCKING...")
    tool_voz = _tool_declarations(non_blocking=True)
    por_nombre = {fd.name: fd.behavior for fd in tool_voz.function_declarations}
    assert por_nombre["buscar_web"] == types.Behavior.NON_BLOCKING, por_nombre
    assert por_nombre["open_app"] == types.Behavior.NON_BLOCKING, por_nombre
    for nombre in ("tareas", "recordatorios", "musica"):
        assert por_nombre[nombre] in (None, types.Behavior.BLOCKING), f"{nombre}: {por_nombre[nombre]!r}"
    print(f"  -> {por_nombre}")

    print("[2b/4] variante de texto (default): ninguna declaración lleva 'behavior' (la API 400 si lo recibe)...")
    tool_texto = _tool_declarations()
    for fd in tool_texto.function_declarations:
        assert fd.behavior is None, f"{fd.name}: 'behavior' no debería ir en la variante de texto ({fd.behavior!r})"
    print("  -> OK, ningún behavior seteado")

    print("[3/4] Caché de Menú Inicio: la segunda llamada no debe volver a escanear el filesystem...")
    open_app_mod._START_MENU_CACHE = None  # arranca en frío, sin importar corridas previas
    t0 = time.monotonic()
    entradas_1 = open_app_mod._load_start_menu_entries()
    t_frio = time.monotonic() - t0
    assert open_app_mod._START_MENU_CACHE is entradas_1, "el primer escaneo no quedó guardado en la caché"

    t0 = time.monotonic()
    resultado = open_app_mod._scan_start_menu("aplicacion_que_no_existe_zzz")
    entradas_2 = open_app_mod._load_start_menu_entries()
    t_cache = time.monotonic() - t0
    # La prueba real de que NO se repitió el rglob es de identidad de objeto,
    # no de timing (un escaneo real puede ser rápido igual si hay pocos
    # accesos directos, y un assert de timing sería flaky) — pero se loguea
    # el tiempo igual porque el plan lo pide como evidencia.
    assert entradas_2 is entradas_1, "la segunda llamada devolvió una lista distinta — volvió a escanear"
    print(f"  -> entradas cacheadas={len(entradas_1)}  frío={t_frio*1000:.1f}ms  "
          f"cache={t_cache*1000:.1f}ms  resultado búsqueda inexistente={resultado!r}")

    print("[4/4] VoiceEngine._lanzar_tool_no_bloqueante: task referenciada, scheduling correcto, respuesta enviada...")
    asyncio.run(_check_dispatch_no_bloqueante())
    print("  -> OK")

    print("OK")


if __name__ == "__main__":
    _check()
