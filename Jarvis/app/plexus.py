"""plexus.py — Render de nube de puntos por matemática, sin ningún asset.

Reemplaza al personaje-sprite (calavera) del paquete de personajes: en vez
de GIFs pregenerados con IA, cada cuadro se calcula en vivo. Eso elimina de
raíz toda la clase de problemas que costó el pipeline anterior (deriva de
identidad entre generaciones, halos por antialiasing del video, paletas GIF
inconsistentes) — ver plans/INVESTIGACION-2026-08-01-overlay-situaciones.md.

Fase 20: la geometría (`app/figuras.py`) es UNA POR ESTADO, no siempre la
misma esfera. Se eliminaron las líneas de conexión (el "plexus" original) a
propósito — medido en plans/INVESTIGACION-2026-08-02-sistema-particulas.md
que su costo O(N²) topaba la densidad en ~140 puntos, y sin líneas 4000
puntos salen MÁS baratos que 90 con líneas (§8.1). Pero sin densidad
suficiente no hay figura reconocible (§8.2) — por eso `N_PUNTOS` subió de
90 a 1200 en el mismo cambio, no por separado.

Restricción que manda sobre todo el diseño: la transparencia del overlay es
por COLOR CLAVE, que es binaria. Ningún píxel puede quedar en un tono
intermedio entre el color clave y el arte, o aparece un halo fantasma. Por
eso acá NADA se dibuja con antialiasing: los nodos son máscaras booleanas de
disco (`dx²+dy² <= r²`), no óvalos de Canvas (el Canvas de Tk sí suaviza los
bordes), y la profundidad se representa con `NIVELES_PROFUNDIDAD` escalones
de color SÓLIDO, no con un degradado continuo. `_check()` verifica esto
contando píxeles en tono intermedio.

Medido en esta máquina a 1200 puntos: ver el print de `_check()`.
"""
from __future__ import annotations

import math
import tkinter as tk

import numpy as np

from app.figuras import N_PUNTOS, catalogo

COLOR_CLAVE = (254, 0, 255)
NIVELES_PROFUNDIDAD = 5

# Brillo del escalón más lejano. Estuvo en 0.35 y sobre fondo oscuro los
# nodos del fondo desaparecían (reportado con captura): 0.35 de un azul
# apagado da (33,44,56), casi el negro del escritorio. 0.55 los mantiene
# legibles sin aplanar la sensación de profundidad.
PISO_BRILLO = 0.55
# Rim lighting: los nodos cerca de la silueta se dibujan más brillantes.
# Es lo que hace que el objeto se despegue del fondo sea cual sea el color
# de atrás, en vez de depender de que el escritorio contraste.
FUERZA_RIM = 0.55

# Un estado = una figura (ver app/figuras.catalogo) + estos parámetros de
# animación. `onda`/`vel_onda` son la deformación de onda viajera de
# 'hablando' (superficie vibrando = emisión) -- no cambian la figura BASE,
# se aplican en tiempo real en `RenderPlexus.frame`. `radio_pt` calibrado
# por figura, no global (medido: los anillos ganan presencia con radio 1,
# la esfera y la onda se empastan con eso — ver investigación §"radio").
ESTADOS = {
    "inactivo":   dict(figura="esfera",      color=(95, 125, 160),  vel_rot=0.25, pulso=0.02,
                       vel_pulso=1.2, ruido=0.03, radio_pt=0, onda=0.0,  vel_onda=0.0),
    "escuchando": dict(figura="toro",        color=(0, 220, 255),   vel_rot=0.55, pulso=0.05,
                       vel_pulso=3.0, ruido=0.03, radio_pt=0, onda=0.0,  vel_onda=0.0),
    "hablando":   dict(figura="esfera",      color=(205, 165, 255), vel_rot=0.85, pulso=0.10,
                       vel_pulso=9.0, ruido=0.03, radio_pt=0, onda=0.17, vel_onda=3.0),
    "procesando": dict(figura="dos_anillos", color=(255, 180, 60),  vel_rot=1.7,  pulso=0.06,
                       vel_pulso=4.0, ruido=0.03, radio_pt=1, onda=0.0,  vel_onda=0.0),
}

# `figura` no es un valor continuo (no tiene sentido "interpolar" el nombre
# de una figura) y `radio_pt` es un entero de tamaño de pixel -- ambos
# cambian de golpe a mitad de camino de la transición en vez de interpolar.
_NO_INTERPOLABLES = {"figura", "radio_pt"}


def mezclar_config(a: dict, b: dict, f: float) -> dict:
    """Interpola dos configs de estado. `f=0` da `a`, `f=1` da `b`. Se usa
    para que al cambiar de estado el color y la animación transicionen
    suave en vez de saltar de golpe (un salto instantáneo se lee como
    glitch). El morph de POSICIONES (entre figuras distintas) es aparte —
    ver `Overlay._puntos_actuales` en overlay.py."""
    f = max(0.0, min(1.0, f))
    salida = {}
    for k, va in a.items():
        vb = b[k]
        if k == "color":
            salida[k] = tuple(va[i] + (vb[i] - va[i]) * f for i in range(3))
        elif k in _NO_INTERPOLABLES:
            salida[k] = vb if f > 0.5 else va
        else:
            salida[k] = va + (vb - va) * f
    return salida


class RenderPlexus:
    def __init__(self, tam: int, n_puntos: int = N_PUNTOS):
        self.tam = tam
        self.n_puntos = n_puntos
        self.catalogo = catalogo(n_puntos)
        # Fases fijas por punto (semilla fija = misma "personalidad" de
        # movimiento en cada arranque, no aleatorio distinto cada vez).
        self.fases = np.random.default_rng(7).uniform(0, 2 * math.pi, n_puntos)
        self._offsets: dict[int, np.ndarray] = {}
        for r in (0, 1, 2, 3):
            dy, dx = np.mgrid[-r:r + 1, -r:r + 1]
            m = (dx * dx + dy * dy) <= r * r
            self._offsets[r] = np.stack([dx[m], dy[m]], axis=1)

    def frame(self, puntos_base: np.ndarray, cfg: dict, t: float) -> np.ndarray:
        """`puntos_base` es la nube YA interpolada entre figuras si hay una
        transición en curso (ver `Overlay._puntos_actuales`). Devuelve un
        cuadro RGB `(tam, tam, 3)` uint8; el fondo es el color clave exacto,
        quien lo muestre se encarga de recortarlo."""
        tam = self.tam
        lienzo = np.empty((tam, tam, 3), dtype=np.uint8)
        lienzo[:, :] = COLOR_CLAVE

        # Deformación orgánica: producto de dos senos desfasados por punto.
        # Da un movimiento fluido tipo ruido, determinista y mucho más
        # barato que un Perlin real (que no aportaría nada perceptible acá).
        respiracion = 1.0 + cfg["pulso"] * math.sin(t * cfg["vel_pulso"])
        deform = 1.0 + cfg["ruido"] * np.sin(t * 1.7 + self.fases) * np.cos(t * 0.9 + self.fases * 1.3)
        pts = puntos_base * (respiracion * deform)[:, None]

        if cfg["onda"]:
            # Onda viajera vertical: el radio de cada punto depende de su
            # altura Y y del tiempo -- da la lectura "superficie vibrando"
            # de 'hablando' sin cambiar la figura base (sigue siendo esfera).
            r_onda = 1.0 + cfg["onda"] * np.sin(pts[:, 1] * 4.0 + t * cfg["vel_onda"])
            pts = pts * r_onda[:, None]

        a = t * cfg["vel_rot"]
        ca, sa = math.cos(a), math.sin(a)
        x = pts[:, 0] * ca + pts[:, 2] * sa
        z = -pts[:, 0] * sa + pts[:, 2] * ca
        y = pts[:, 1]
        # Inclinación fija: sin esto la figura se ve girando "de frente" y
        # plana; inclinada se lee el volumen.
        inc = 0.42
        ci, si = math.cos(inc), math.sin(inc)
        y, z = y * ci - z * si, y * si + z * ci

        dist_cam = 3.2
        escala = tam * 0.34
        f = dist_cam / (dist_cam - z)
        px = x * f * escala + tam / 2
        py = y * f * escala + tam / 2

        z_norm = (z - z.min()) / max(float(np.ptp(z)), 1e-6)
        nivel = np.clip((z_norm * NIVELES_PROFUNDIDAD).astype(int), 0, NIVELES_PROFUNDIDAD - 1)
        factor = np.linspace(PISO_BRILLO, 1.0, NIVELES_PROFUNDIDAD)[nivel]

        # Rim lighting: cuanto más lejos del centro proyectado, más brillo.
        # El `**3` concentra el efecto en el borde real de la silueta en vez
        # de aclarar todo el objeto de forma pareja.
        radio_proy = np.sqrt((px - tam / 2) ** 2 + (py - tam / 2) ** 2)
        borde = radio_proy / max(float(radio_proy.max()), 1e-6)
        factor = np.clip(factor + FUERZA_RIM * borde ** 3, 0.0, 1.0)

        base_color = np.array(cfg["color"], dtype=np.float64)
        col_nodo_pt = np.clip(base_color[None, :] * factor[:, None], 0, 255).astype(np.uint8)

        off = self._offsets[int(round(cfg["radio_pt"]))]
        nx = px.round().astype(int)[:, None] + off[None, :, 0]
        ny = py.round().astype(int)[:, None] + off[None, :, 1]
        dentro = (nx >= 0) & (nx < tam) & (ny >= 0) & (ny < tam)
        col_nodo = np.repeat(col_nodo_pt[:, None, :], off.shape[0], axis=1)
        lienzo[ny[dentro], nx[dentro]] = col_nodo[dentro]

        return lienzo


def a_photoimage(lienzo: np.ndarray) -> tk.PhotoImage:
    """numpy -> PhotoImage vía PPM crudo (P6). Tk lo lee nativo, sin Pillow
    y sin pasar por disco."""
    tam = lienzo.shape[0]
    cabecera = f"P6 {tam} {tam} 255 ".encode("ascii")
    return tk.PhotoImage(data=cabecera + lienzo.tobytes(), format="PPM")


def _check() -> None:
    """Self-check sin ventana: geometría, interpolación, rendimiento y —lo
    que más importa— que no queden píxeles en tono intermedio (halo)."""
    import time

    r = RenderPlexus(150, n_puntos=300)

    for nombre, pts in r.catalogo.items():
        assert pts.shape == (300, 3), f"{nombre}: forma incorrecta en el catálogo"

    a, b = ESTADOS["inactivo"], ESTADOS["hablando"]
    assert mezclar_config(a, b, 0.0)["color"] == tuple(float(c) for c in a["color"]), "f=0 debería dar el estado A"
    assert mezclar_config(a, b, 1.0)["color"] == tuple(float(c) for c in b["color"]), "f=1 debería dar el estado B"
    medio = mezclar_config(a, b, 0.5)
    assert a["vel_rot"] < medio["vel_rot"] < b["vel_rot"], "la interpolación debería quedar entre ambos"
    assert mezclar_config(a, b, 5.0)["color"] == tuple(float(c) for c in b["color"]), "f fuera de rango debe clampear"
    assert mezclar_config(a, b, 0.3)["figura"] == a["figura"], "figura no debería cambiar antes de f=0.5"
    assert mezclar_config(a, b, 0.7)["figura"] == b["figura"], "figura debería cambiar después de f=0.5"

    for estado, cfg in ESTADOS.items():
        pts = r.catalogo[cfg["figura"]]
        lienzo = r.frame(pts, cfg, 3.7)
        assert lienzo.shape == (150, 150, 3), f"{estado}: forma de cuadro incorrecta"
        plano = lienzo.reshape(-1, 3).astype(np.int16)
        d = np.linalg.norm(plano - np.array(COLOR_CLAVE, dtype=np.int16), axis=1)
        # Un píxel o es fondo (d≈0) o es arte (d grande). Nada en el medio,
        # o el color-key deja un halo alrededor de cada nodo.
        intermedios = int(((d > 12) & (d < 90)).sum())
        assert intermedios == 0, f"{estado}: {intermedios} píxeles de halo (borde no duro)"
        assert (d > 90).sum() > 50, f"{estado}: el cuadro salió casi vacío"

    # Rendimiento real a la densidad de producción (N_PUNTOS=1200).
    r_prod = RenderPlexus(150)
    for estado, cfg in ESTADOS.items():
        pts = r_prod.catalogo[cfg["figura"]]
        r_prod.frame(pts, cfg, 0.0)  # calienta
        t0 = time.perf_counter()
        for i in range(60):
            r_prod.frame(pts, cfg, i * 0.033)
        ms = (time.perf_counter() - t0) / 60 * 1000
        print(f"  {estado:11} {ms:5.2f} ms/frame")

    print("OK")


if __name__ == "__main__":
    _check()
