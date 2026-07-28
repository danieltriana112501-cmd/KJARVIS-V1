"""convertir_ascii.py — Herramienta de desarrollo (Fase 09, Modo A), NO se
ejecuta en runtime de la app. Convierte un video/gif en una secuencia de
frames de arte ASCII para reemplazar/complementar en el futuro el frame
único de `Jarvis/assets/skull_frame.json` (Fase 09, sección 0).

Uso:
    python convertir_ascii.py entrada.mp4 salida.json --cols 100 --fps 12

Requiere `opencv-python` (no listado en requirements.txt del proyecto: solo
hace falta instalarlo si de verdad se usa este script con un archivo nuevo,
ver plans/phase-09-ascii-panel.md sección "Alcance de esta fase", punto 1).

Salida: JSON `{"fps": N, "frames": [["fila1", "fila2", ...], ...]}`, listo
para que `Jarvis/assets/app.js` lo reproduzca en loop a `1000/fps` ms.
"""
from __future__ import annotations

import argparse
import json
import sys

RAMPA = " .:-=+*#%@"
# Un carácter monoespaciado es ~2x más alto que ancho: se compensa el
# muestreo vertical con este factor para no ver la imagen "estirada".
FACTOR_ASPECTO_CHAR = 0.55


def frame_a_ascii(frame_gray, cols: int) -> list[str]:
    alto, ancho = frame_gray.shape
    filas = max(1, round(cols * (alto / ancho) * FACTOR_ASPECTO_CHAR))

    import cv2
    redimensionado = cv2.resize(frame_gray, (cols, filas))

    lineas = []
    for fila in redimensionado:
        linea = "".join(RAMPA[int(pixel) * (len(RAMPA) - 1) // 255] for pixel in fila)
        lineas.append(linea)
    return lineas


def convertir(entrada: str, salida: str, cols: int, fps: int) -> None:
    import cv2

    cap = cv2.VideoCapture(entrada)
    if not cap.isOpened():
        sys.exit(f"No se pudo abrir '{entrada}'.")

    fps_origen = cap.get(cv2.CAP_PROP_FPS) or fps
    salto = max(1, round(fps_origen / fps))

    frames = []
    indice = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if indice % salto == 0:
            gris = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            frames.append(frame_a_ascii(gris, cols))
        indice += 1
    cap.release()

    if not frames:
        sys.exit("No se extrajo ningún frame (¿archivo vacío o formato no soportado?).")

    with open(salida, "w", encoding="utf-8") as f:
        json.dump({"fps": fps, "frames": frames}, f, ensure_ascii=False)

    print(f"OK: {len(frames)} frames -> {salida}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Convierte un video/gif a arte ASCII animado (JSON).")
    parser.add_argument("entrada")
    parser.add_argument("salida")
    parser.add_argument("--cols", type=int, default=100)
    parser.add_argument("--fps", type=int, default=12)
    args = parser.parse_args()
    convertir(args.entrada, args.salida, args.cols, args.fps)


if __name__ == "__main__":
    main()
