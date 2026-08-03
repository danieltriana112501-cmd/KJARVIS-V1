"""figuras.py — catálogo de nubes de puntos, una por estado (Fase 20).

Ver plans/INVESTIGACION-2026-08-02-sistema-particulas.md. Reglas que manda
la investigación:
  - Curva antes que superficie (§4, §8.2): con puntos fijos, una curva 1D
    concentra densidad; una superficie 2D la dispersa.
  - Nada de superformas de Gielis -- refutadas dos veces, con dos sistemas
    y a 40x la densidad (§3, §8.5). No reintentar.
  - Farthest-point sampling no aporta a esta escala -- grilla densa +
    submuestreo aleatorio alcanza (§3).

Todas las figuras devuelven `(n, 3)` normalizado a que `abs().max() == 1`
(mismo contrato que la vieja `_esfera_fibonacci` de `plexus.py`).
"""
from __future__ import annotations

import math

import numpy as np

N_PUNTOS = 1200


def _fibonacci(n: int) -> np.ndarray:
    """Puntos reparto parejo sobre la esfera (espiral de Fibonacci). Se usa
    esto y no lat/long al azar porque lat/long amontona puntos en los polos
    y se nota feo al rotar."""
    i = np.arange(n, dtype=np.float64)
    angulo_aureo = math.pi * (3.0 - math.sqrt(5.0))
    y = 1.0 - (i / (n - 1)) * 2.0
    radio_fila = np.sqrt(np.clip(1.0 - y * y, 0.0, 1.0))
    theta = angulo_aureo * i
    return np.stack([np.cos(theta) * radio_fila, y, np.sin(theta) * radio_fila], axis=1)


def _submuestrear(p: np.ndarray, n: int, semilla: int = 2) -> np.ndarray:
    if len(p) <= n:
        return p
    rng = np.random.default_rng(semilla)
    return p[rng.choice(len(p), n, replace=False)]


def _normalizar(p: np.ndarray) -> np.ndarray:
    return p / max(float(np.abs(p).max()), 1e-9)


def esfera(n: int = N_PUNTOS) -> np.ndarray:
    """`inactivo` -- neutra, en reposo."""
    return _fibonacci(n)


def toro(n: int = N_PUNTOS, radio_mayor: float = 0.72, radio_menor: float = 0.3) -> np.ndarray:
    """`escuchando` -- se abre hacia afuera, receptivo; el agujero la hace
    inconfundible frente a la esfera. Grilla U/V densa, submuestreada."""
    g = int(math.sqrt(n * 2)) + 2
    u = np.linspace(0, 2 * math.pi, g, endpoint=False)
    uu, vv = np.meshgrid(u, u)
    uu, vv = uu.ravel(), vv.ravel()
    x = (radio_mayor + radio_menor * np.cos(vv)) * np.cos(uu)
    y = radio_menor * np.sin(vv)
    z = (radio_mayor + radio_menor * np.cos(vv)) * np.sin(uu)
    return _normalizar(_submuestrear(np.stack([x, y, z], axis=1), n))


def dos_anillos(n: int = N_PUNTOS) -> np.ndarray:
    """`procesando` -- dos anillos perpendiculares, lee como giroscopio /
    maquinaria trabajando. La figura de curva más nítida medida (§4, §8.6)."""
    mitad = n // 2
    t = np.linspace(0, 2 * math.pi, mitad, endpoint=False)
    a1 = np.stack([np.cos(t), np.sin(t), np.zeros_like(t)], axis=1)
    a2 = np.stack([np.cos(t), np.zeros_like(t), np.sin(t)], axis=1)
    p = np.vstack([a1, a2])
    if len(p) < n:  # n impar: un punto de más del primer anillo lo completa
        p = np.vstack([p, a1[:1]])
    return _normalizar(p)


def ordenar_por_angulo(p: np.ndarray) -> np.ndarray:
    """Reordena una nube por posición angular respecto al origen -- da una
    correspondencia índice-a-índice razonable entre nubes DISTINTAS, sin
    que compartan parametrización. Método validado en
    plans/INVESTIGACION-2026-08-02-sistema-particulas.md sección 5: permite
    morphear entre figuras interpolando posiciones sin que la nube "explote"
    a mitad de camino."""
    theta = np.arctan2(p[:, 2], p[:, 0])
    escala = max(float(np.abs(p[:, 1]).max()), 1e-9)
    phi = np.arcsin(np.clip(p[:, 1] / escala, -1.0, 1.0))
    orden = np.lexsort((theta, np.round(phi, 1)))
    return p[orden]


def catalogo(n: int = N_PUNTOS) -> dict[str, np.ndarray]:
    """Las figuras del catálogo, todas con exactamente `n` puntos y
    reordenadas por ángulo para que el morph entre cualquier par sea una
    interpolación índice-a-índice coherente."""
    crudas = {
        "esfera": esfera(n),
        "toro": toro(n),
        "dos_anillos": dos_anillos(n),
    }
    return {nombre: ordenar_por_angulo(pts) for nombre, pts in crudas.items()}


def _check() -> None:
    cat = catalogo(300)
    for nombre, pts in cat.items():
        assert pts.shape == (300, 3), f"{nombre}: forma incorrecta {pts.shape}"
        assert np.abs(pts).max() <= 1.0 + 1e-6, f"{nombre}: no está normalizada"
        assert np.isfinite(pts).all(), f"{nombre}: tiene NaN/inf"

    # dos_anillos con n impar no debe perder ni duplicar de más
    assert len(dos_anillos(300)) == 300
    assert len(dos_anillos(301)) == 301

    # el reordenado por ángulo es una permutación, no pierde ni inventa puntos
    cruda = toro(300)
    ordenada = ordenar_por_angulo(cruda)
    assert ordenada.shape == cruda.shape
    assert np.allclose(sorted(cruda.tolist()), sorted(ordenada.tolist()))

    print("OK")


if __name__ == "__main__":
    _check()
