"""overlay.py — Esfera de plexus flotante en el escritorio (Fase 19).

Reemplaza la ventana mini pywebview de la Fase 10 (rota en Windows:
pywebview ignora `transparent=True` en ese backend, ver
plans/INVESTIGACION-2026-07-27-voz-tools-ui.md sección 10.2). Corre como
PROCESO APARTE (lanzado por `ui.py` vía subprocess) porque Tk y pywebview
compiten mal por el hilo principal — ver sección 10.5 de esa investigación.

Es un cliente tonto: solo hace polling de `/api/estado` y `/api/pip/estado`
contra el Flask que ya expone `server.py`. No importa nada de
`voice_engine.py` ni `gemini_agent.py` — si este proceso crashea, Jarvis
sigue funcionando.

El arte lo genera `plexus.py` por matemática en vivo (no hay assets) — una
figura distinta por estado desde la Fase 20 (`app/figuras.py`), no siempre
la misma esfera. Los tres bugs de Windows que costaron encontrar están
documentados en plans/INVESTIGACION-2026-08-01-overlay-situaciones.md
sección 1:
  1. El Label NUNCA debe arrancar sin `image=` -- si arranca vacío y se le
     asigna una imagen recién en el primer tick, la ventana queda negra
     sólida para siempre, sin que `.configure()` después lo arregle.
  2. Activar click-through con `SetWindowLongW` pisa el color-key que Tk ya
     configuró para `-transparentcolor` -- hay que re-aplicar
     `SetLayeredWindowAttributes` con `LWA_COLORKEY` después.
  3. Pedir el HWND antes de `root.update_idletasks()` puede dar un handle
     inválido que falla en silencio (sin excepción).
  4. Los binds `<Button-1>` de Tk NO alcanzan para arrastrar: el color-key
     deja pasar los clics sobre los píxeles transparentes, que son casi
     toda la ventana. El arrastre se hace por polling -- ver
     `_revisar_arrastre`.

También registra el atajo global Ctrl+Espacio para iniciar/detener la
sesión de voz sin tocar la ventana principal -- se revisa por polling de
`GetAsyncKeyState` (igual que el resto del módulo, que ya hace polling para
todo) en vez de `RegisterHotKey`/enganchar el mensaje `WM_HOTKEY`: evita
subclasear el WndProc de Tk, y funciona sin importar qué ventana tenga el
foco porque `GetAsyncKeyState` lee el estado físico del teclado, no eventos
de una ventana en particular.
"""
from __future__ import annotations

import ctypes
import json
import random
import sys
import time
import tkinter as tk
import urllib.request

import numpy as np

from app.figuras import ordenar_por_angulo
from app.plexus import COLOR_CLAVE, ESTADOS, RenderPlexus, a_photoimage, mezclar_config

PUERTO = 5577
API_ESTADO = f"http://127.0.0.1:{PUERTO}/api/estado"
API_PIP_ESTADO = f"http://127.0.0.1:{PUERTO}/api/pip/estado"
API_VOZ_ESTADO = f"http://127.0.0.1:{PUERTO}/api/voz/estado"
API_VOZ_INICIAR = f"http://127.0.0.1:{PUERTO}/api/voz/iniciar"
API_VOZ_DETENER = f"http://127.0.0.1:{PUERTO}/api/voz/detener"

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x80000
WS_EX_TRANSPARENT = 0x20
LWA_COLORKEY = 0x1

VK_LBUTTON = 0x01
VK_CONTROL = 0x11
VK_SPACE = 0x20

TAM = 150
FPS = 30
DURACION_TRANSICION_S = 0.6   # cuánto tarda en morphear de un estado a otro

MARGEN_BORDE = 24          # distancia del ancla de reposo a la esquina de pantalla
RADIO_DERIVA_PX = 10       # deriva sutil alrededor del ancla -- NO deambula por la pantalla
INTERVALO_DERIVA_MS = (6000, 12000)
PASO_DERIVA_PX = 1         # px por tick -- lento y deliberado, no errático
INTERVALO_MOVIMIENTO_MS = 40
INTERVALO_POLL_MS = 500
# 60 polls de 500ms = 30s sin poder hablarle al servidor -> el overlay se
# cierra solo. Sin esto, cuando la ventana principal moría sin pasar por el
# `finally` de ui.py (crash, kill, cierre forzado) el overlay quedaba
# huérfano: la esfera seguía flotando sin app detrás, y el próximo arranque
# sumaba otra encima (se llegaron a ver tres a la vez).
FALLOS_MAX_SERVIDOR = 60
INTERVALO_CLICKTHROUGH_MS = 100
INTERVALO_ATAJO_MS = 50    # revisar el estado del teclado seguido para que el atajo se sienta responsive
INTERVALO_ARRASTRE_MS = 16 # ~60fps: menos que esto y el arrastre se ve a los saltos


ERROR_ALREADY_EXISTS = 183
NOMBRE_MUTEX = "JarvisOverlayInstanciaUnica"


def _tomar_instancia_unica(nombre: str = NOMBRE_MUTEX) -> bool:
    """True si este proceso es el ÚNICO overlay vivo.

    Segunda mitad del arreglo de las esferas duplicadas: aunque el overlay
    ahora se cierre solo cuando el servidor desaparece, entre el arranque de
    uno nuevo y la muerte del viejo hay una ventana en la que conviven. El
    mutex con nombre la cierra: el segundo proceso ve ERROR_ALREADY_EXISTS y
    se va sin abrir ventana.

    El handle queda abierto a propósito -- Windows libera el mutex cuando el
    proceso termina, así que no hay nada que limpiar (y limpiarlo sería peor:
    liberaría el nombre con el overlay todavía vivo).
    """
    if not hasattr(ctypes, "windll"):
        return True  # fuera de Windows no hay mutex con nombre; no bloquear
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, nombre)
    if not handle:
        return True  # no se pudo crear: mejor arrancar que quedarse mudo
    return ctypes.windll.kernel32.GetLastError() != ERROR_ALREADY_EXISTS


def _color_hex(rgb: tuple[int, int, int]) -> str:
    return "#%02X%02X%02X" % rgb


def _colorref(rgb: tuple[int, int, int]) -> int:
    """RGB -> COLORREF de Windows (0x00BBGGRR)."""
    r, g, b = rgb
    return (b << 16) | (g << 8) | r


def _aplicar_click_through(hwnd: int, activo: bool, colorref: int) -> None:
    """Prende o apaga el paso-a-través de clics. SIEMPRE re-aplica el
    color-key después de tocar el estilo extendido -- ver punto 2 del
    docstring del módulo, es el bug que más costó encontrar."""
    estilo = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    if activo:
        estilo |= WS_EX_TRANSPARENT
    else:
        estilo &= ~WS_EX_TRANSPARENT
    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, estilo | WS_EX_LAYERED)
    ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, colorref, 0, LWA_COLORKEY)


def _posicion_dock(pantalla_ancho: int, pantalla_alto: int, tam_ventana: int) -> tuple[int, int]:
    """Ancla de reposo FIJA en la esquina inferior derecha -- no deambula por
    toda la pantalla (eso lee como proceso fuera de control, no como widget).
    Función pura -- ver `_check()`."""
    x = max(MARGEN_BORDE, pantalla_ancho - tam_ventana - MARGEN_BORDE)
    y = max(MARGEN_BORDE, pantalla_alto - tam_ventana - MARGEN_BORDE)
    return x, y


def _punto_deriva(ancla_x: int, ancla_y: int, radio: int) -> tuple[int, int]:
    """Micro-movimiento alrededor del ancla. Función pura -- ver `_check()`."""
    return ancla_x + random.randint(-radio, radio), ancla_y + random.randint(-radio, radio)


def _mouse_sobre_ventana(mouse_x: int, mouse_y: int, ventana_x: int, ventana_y: int, tam: int) -> bool:
    """Función pura -- ver `_check()`."""
    return ventana_x <= mouse_x <= ventana_x + tam and ventana_y <= mouse_y <= ventana_y + tam


def _tecla_presionada(vk: int) -> bool:
    """Estado FÍSICO actual de una tecla, sin importar qué ventana tiene el
    foco -- es lo que hace que Ctrl+Espacio funcione como atajo global."""
    return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)


def _interpolar_nube(a: np.ndarray, b: np.ndarray, f: float) -> np.ndarray:
    """Interpola posiciones entre dos nubes de la MISMA longitud, ya
    reordenadas por ángulo (`figuras.ordenar_por_angulo`) para que el
    índice i de una corresponda al índice i de la otra. Función pura --
    ver `_check()`."""
    f = max(0.0, min(1.0, f))
    return a + (b - a) * f


class Overlay:
    def __init__(self, tam: int = TAM):
        self.tam = tam
        self.clave_hex = _color_hex(COLOR_CLAVE)
        self.render = RenderPlexus(tam)
        self.t0 = time.monotonic()

        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.configure(bg=self.clave_hex)
        self.root.wm_attributes("-transparentcolor", self.clave_hex)
        self.root.wm_attributes("-topmost", True)

        pantalla_ancho = self.root.winfo_screenwidth()
        pantalla_alto = self.root.winfo_screenheight()
        self.ancla_x, self.ancla_y = _posicion_dock(pantalla_ancho, pantalla_alto, tam)
        self.x, self.y = self.ancla_x, self.ancla_y
        self.root.geometry(f"{tam}x{tam}+{self.x}+{self.y}")

        # Estado + transición: al cambiar, se interpola de `cfg_desde` a
        # `estado` durante DURACION_TRANSICION_S para que el color/animación
        # sea un morph y no un salto. `figura_desde` es lo mismo pero para
        # las POSICIONES (ver `_puntos_actuales`): arranca cada transición
        # desde la nube interpolada actual, no desde la figura vieja
        # completa, para que un cambio de estado a mitad de otra transición
        # no salte hacia atrás.
        self.estado = "inactivo"
        self.cfg_desde = dict(ESTADOS["inactivo"])
        self.figura_desde = self.render.catalogo[ESTADOS["inactivo"]["figura"]]
        self.t_cambio = -999.0

        # El Label NUNCA arranca vacío -- ver punto 1 del docstring.
        cfg0 = ESTADOS["inactivo"]
        primer_frame = a_photoimage(self.render.frame(self.render.catalogo[cfg0["figura"]], cfg0, 0.0))
        self.label = tk.Label(self.root, image=primer_frame, bg=self.clave_hex, bd=0)
        self.label.image = primer_frame
        self.label.pack()

        self.visible = True
        self.arrastrando = False
        self.click_through_activo = True
        self.destino: tuple[int, int] | None = None
        self.atajo_presionado_antes = False
        self.boton_presionado_antes = False
        self._offset = (0, 0)
        self.hubo_contacto = False
        self.fallos_seguidos = 0

        self.root.update_idletasks()  # antes de tocar el hwnd -- ver punto 3
        self.hwnd = self.root.winfo_id()
        self.colorref = _colorref(COLOR_CLAVE)
        _aplicar_click_through(self.hwnd, True, self.colorref)

    # ---------------- arrastre ----------------

    def _revisar_arrastre(self) -> None:
        """Arrastre por polling del botón físico del mouse, NO por eventos
        `<Button-1>` de Tk.

        Los binds de Tk no servían: `-transparentcolor` activa
        `LWA_COLORKEY`, y Windows deja pasar los clics sobre los píxeles del
        color clave sin importar `WS_EX_TRANSPARENT`. Como el arte es una
        nube de puntos (casi toda la ventana es color clave), había que
        acertarle a un punto encendido para agarrarla -- en la práctica la
        ventana no se podía mover (reportado probando la app real).

        Leyendo `GetAsyncKeyState(VK_LBUTTON)` el arrastre no depende del
        hit-testing de Windows: alcanza con que el cursor esté dentro del
        rectángulo de la ventana. Mismo mecanismo que Ctrl+Espacio.
        """
        presionado = _tecla_presionada(VK_LBUTTON)
        mx, my = self.root.winfo_pointerx(), self.root.winfo_pointery()

        if presionado and not self.boton_presionado_antes:
            # Flanco de bajada: solo agarra si el cursor está sobre la ventana.
            if self.visible and _mouse_sobre_ventana(mx, my, self.x, self.y, self.tam):
                self.arrastrando = True
                self._offset = (mx - self.x, my - self.y)
                self.destino = None  # cancela la deriva mientras se arrastra
        elif not presionado and self.arrastrando:
            self.arrastrando = False
            # El nuevo ancla es donde el usuario la soltó: si volviera sola a
            # la esquina se sentiría como perder control sobre el proceso.
            self.ancla_x, self.ancla_y = self.x, self.y

        if self.arrastrando:
            self.x = mx - self._offset[0]
            self.y = my - self._offset[1]
            self.root.geometry(f"+{self.x}+{self.y}")

        self.boton_presionado_antes = presionado
        self.root.after(INTERVALO_ARRASTRE_MS, self._revisar_arrastre)

    # ---------------- polling ----------------

    def _poll_estado(self) -> None:
        contacto = False
        try:
            with urllib.request.urlopen(API_ESTADO, timeout=1) as resp:
                nuevo = json.loads(resp.read()).get("estado", "inactivo")
            contacto = True
            if nuevo not in ESTADOS:
                nuevo = "inactivo"
            if nuevo != self.estado:
                # Arranca la transición desde la config/posiciones
                # INTERPOLADAS actuales, no desde las del estado anterior:
                # si llega un cambio a mitad de otra transición, no salta
                # hacia atrás.
                self.cfg_desde = self._cfg_actual()
                self.figura_desde = self._puntos_actuales()
                self.estado = nuevo
                self.t_cambio = time.monotonic()
        except Exception:
            pass  # servidor caído/arrancando -- se reintenta solo

        try:
            with urllib.request.urlopen(API_PIP_ESTADO, timeout=1) as resp:
                habilitado = json.loads(resp.read()).get("habilitado", True)
            contacto = True
            if habilitado != self.visible:
                self.visible = habilitado
                (self.root.deiconify() if habilitado else self.root.withdraw())
        except Exception:
            pass

        if self._servidor_se_fue(contacto):
            self.root.destroy()  # corta el mainloop: el proceso termina
            return

        self.root.after(INTERVALO_POLL_MS, self._poll_estado)

    def _servidor_se_fue(self, contacto: bool) -> bool:
        """True cuando hay que darse por muerto: el servidor respondió alguna
        vez y después dejó de responder por `FALLOS_MAX_SERVIDOR` polls
        seguidos.

        El `hubo_contacto` importa: al arrancar, `ui.py` lanza este proceso
        justo antes de levantar Flask, así que los primeros polls fallan
        siempre y no hay que cerrarse por eso.
        """
        if contacto:
            self.hubo_contacto = True
            self.fallos_seguidos = 0
            return False
        if not self.hubo_contacto:
            return False
        self.fallos_seguidos += 1
        return self.fallos_seguidos >= FALLOS_MAX_SERVIDOR

    def _cfg_actual(self) -> dict:
        f = (time.monotonic() - self.t_cambio) / DURACION_TRANSICION_S
        return mezclar_config(self.cfg_desde, ESTADOS[self.estado], f)

    def _puntos_actuales(self) -> np.ndarray:
        """Nube de puntos interpolada entre la figura de origen y la del
        estado actual (mismo `f` que `_cfg_actual`, mismo mecanismo de
        transición) -- ver `figuras.ordenar_por_angulo` para por qué
        interpolar índice-a-índice entre figuras distintas no rompe la
        nube a mitad de camino."""
        f = (time.monotonic() - self.t_cambio) / DURACION_TRANSICION_S
        figura_destino = self.render.catalogo[ESTADOS[self.estado]["figura"]]
        return _interpolar_nube(self.figura_desde, figura_destino, f)

    def _animar(self) -> None:
        if self.visible:
            t = time.monotonic() - self.t0
            imagen = a_photoimage(self.render.frame(self._puntos_actuales(), self._cfg_actual(), t))
            self.label.configure(image=imagen)
            self.label.image = imagen  # referencia fuerte: sin esto Tk la recolecta y no se ve nada
        self.root.after(int(1000 / FPS), self._animar)

    # ---------------- click-through dinámico ----------------

    def _revisar_click_through(self) -> None:
        mx, my = self.root.winfo_pointerx(), self.root.winfo_pointery()
        sobre = _mouse_sobre_ventana(mx, my, self.x, self.y, self.tam)
        deberia_pasar_clics = not sobre and not self.arrastrando
        if deberia_pasar_clics != self.click_through_activo:
            self.click_through_activo = deberia_pasar_clics
            _aplicar_click_through(self.hwnd, deberia_pasar_clics, self.colorref)
        self.root.after(INTERVALO_CLICKTHROUGH_MS, self._revisar_click_through)

    # ---------------- atajo global Ctrl+Espacio: iniciar/detener voz ----------------

    def _revisar_atajo_microfono(self) -> None:
        presionado = _tecla_presionada(VK_CONTROL) and _tecla_presionada(VK_SPACE)
        if presionado and not self.atajo_presionado_antes:
            self._alternar_microfono()
        self.atajo_presionado_antes = presionado
        self.root.after(INTERVALO_ATAJO_MS, self._revisar_atajo_microfono)

    def _alternar_microfono(self) -> None:
        """Dispara en el flanco de subida (tecla recién apretada), no
        mientras se mantiene apretada -- sin el flag `atajo_presionado_antes`
        esto llamaría a iniciar/detener decenas de veces por segundo
        mientras el usuario sostiene la combinación."""
        try:
            with urllib.request.urlopen(API_VOZ_ESTADO, timeout=1) as resp:
                activo = json.loads(resp.read()).get("activo", False)
            endpoint = API_VOZ_DETENER if activo else API_VOZ_INICIAR
            peticion = urllib.request.Request(endpoint, data=b"", method="POST")
            urllib.request.urlopen(peticion, timeout=5)
        except Exception:
            pass  # servidor caído/arrancando -- el atajo simplemente no hizo nada esta vez

    # ---------------- deriva sutil ----------------

    def _elegir_destino(self) -> None:
        if not self.arrastrando:
            self.destino = _punto_deriva(self.ancla_x, self.ancla_y, RADIO_DERIVA_PX)
        self.root.after(random.randint(*INTERVALO_DERIVA_MS), self._elegir_destino)

    def _mover_hacia_destino(self) -> None:
        if self.destino is not None and not self.arrastrando:
            dx, dy = self.destino
            self.x += max(-PASO_DERIVA_PX, min(PASO_DERIVA_PX, dx - self.x))
            self.y += max(-PASO_DERIVA_PX, min(PASO_DERIVA_PX, dy - self.y))
            self.root.geometry(f"+{self.x}+{self.y}")
            if (self.x, self.y) == self.destino:
                self.destino = None
        self.root.after(INTERVALO_MOVIMIENTO_MS, self._mover_hacia_destino)

    def correr(self) -> None:
        self._poll_estado()
        self._animar()
        self._revisar_click_through()
        self._revisar_atajo_microfono()
        self._revisar_arrastre()
        self._elegir_destino()
        self._mover_hacia_destino()
        self.root.mainloop()


def main() -> None:
    if not _tomar_instancia_unica():
        return  # ya hay un overlay vivo -- no abrir una segunda esfera
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # antes de crear cualquier Tk()
    except Exception:
        pass  # Windows viejo sin shcore: funciona igual, solo sin DPI awareness
    Overlay().correr()


def _check() -> None:
    """Self-check de la lógica pura (sin abrir ninguna ventana real)."""
    x, y = _posicion_dock(1920, 1080, 150)
    assert x == 1920 - 150 - MARGEN_BORDE, "ancla x debería pegarse a la esquina derecha"
    assert y == 1080 - 150 - MARGEN_BORDE, "ancla y debería pegarse a la esquina inferior"

    x2, y2 = _posicion_dock(100, 100, 200)
    assert x2 == MARGEN_BORDE and y2 == MARGEN_BORDE, "pantalla chica debería colapsar al margen"

    for _ in range(20):
        dx, dy = _punto_deriva(500, 500, RADIO_DERIVA_PX)
        assert abs(dx - 500) <= RADIO_DERIVA_PX, "deriva x se fue del radio permitido"
        assert abs(dy - 500) <= RADIO_DERIVA_PX, "deriva y se fue del radio permitido"

    assert _mouse_sobre_ventana(150, 150, 100, 100, 200) is True, "debería estar adentro"
    assert _mouse_sobre_ventana(50, 50, 100, 100, 200) is False, "debería estar afuera (antes)"
    assert _mouse_sobre_ventana(301, 150, 100, 100, 200) is False, "debería estar afuera (después)"
    assert _mouse_sobre_ventana(100, 100, 100, 100, 200) is True, "borde exacto cuenta como adentro"

    assert _colorref((254, 0, 255)) == 0xFF00FE, "COLORREF mal armado (debe ser 0x00BBGGRR)"
    assert _color_hex((254, 0, 255)) == "#FE00FF", "hex mal armado"

    a = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]])
    b = np.array([[2.0, 2.0, 2.0], [4.0, 4.0, 4.0]])
    assert np.allclose(_interpolar_nube(a, b, 0.0), a), "f=0 debería dar la nube A"
    assert np.allclose(_interpolar_nube(a, b, 1.0), b), "f=1 debería dar la nube B"
    assert np.allclose(_interpolar_nube(a, b, 0.5), (a + b) / 2), "f=0.5 debería ser el punto medio"
    assert np.allclose(_interpolar_nube(a, b, 5.0), b), "f fuera de rango debe clampear"

    # Instancia única: el primer CreateMutexW gana, el segundo (mismo nombre)
    # tiene que perder. Nombre propio del test para no pelear con un overlay
    # real que esté corriendo mientras se corre el check.
    nombre_test = NOMBRE_MUTEX + "Check"
    assert _tomar_instancia_unica(nombre_test) is True, "el primero debería tomar la instancia"
    assert _tomar_instancia_unica(nombre_test) is False, "el segundo debería rebotar"

    # Muerte por servidor ausente. Se prueba sobre un objeto pelado: la lógica
    # solo toca dos contadores, no hace falta levantar una ventana real.
    class _Falso:
        hubo_contacto = False
        fallos_seguidos = 0
        _servidor_se_fue = Overlay._servidor_se_fue

    f = _Falso()
    for _ in range(FALLOS_MAX_SERVIDOR + 5):
        assert f._servidor_se_fue(False) is False, "sin contacto previo nunca debe cerrarse"
    assert f._servidor_se_fue(True) is False, "con contacto no debe cerrarse"
    assert f.fallos_seguidos == 0, "un contacto exitoso debe resetear el contador"
    for i in range(FALLOS_MAX_SERVIDOR - 1):
        assert f._servidor_se_fue(False) is False, f"no debe cerrarse todavía (fallo {i + 1})"
    assert f._servidor_se_fue(False) is True, "al llegar al máximo de fallos debe cerrarse"

    print("OK")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        _check()
    else:
        main()
