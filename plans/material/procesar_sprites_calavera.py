"""Pipeline mp4 (Veo3) -> GIF con transparencia real por color clave, para
los 4 estados de la calavera. Ver plans/material/prompts-veo3-animacion-
calavera.md (post-proceso) y plans/INVESTIGACION-2026-07-27-voz-tools-ui.md
seccion 13 (formato del paquete de personaje).

A diferencia del plan original (arte 2-tonos B/N), el resultado real de
Veo3 trae sombreado gris tipo comic (ver contact sheets) -- eso se
conserva tal cual, NO se umbraliza a blanco/negro puro. Lo unico que se
trata especial es el FONDO: se reemplaza por el color clave EXACTO
(#FF00FE) con tolerancia de distancia de color, porque el fondo real tiene
gradiente/textura, no es plano.

Requiere opencv-python-headless (pip install opencv-python-headless) --
no esta en requirements.txt porque solo hace falta para regenerar los
sprites, no para correr la app.
"""
import cv2
import numpy as np
from PIL import Image

CARPETA_ORIGEN = r"C:\Users\danie\Videos\JARVIS\Jarvis-Desktop-Voice-Assistant\plans\material\videos-fuente-calavera"
CARPETA_DESTINO = r"C:\Users\danie\Videos\JARVIS\Jarvis-Desktop-Voice-Assistant\Jarvis\assets\personajes\calavera"

COLOR_CLAVE = (254, 0, 255)  # #FF00FE en RGB
TAMANO_FINAL = 200

# nombre_archivo, fps_destino, n_frames_gif, (frame_inicio, frame_fin|None)
ESTADOS = {
    "inactivo":   ("Inactivo.mp4",   8,  10, (0, None)),
    "escuchando": ("Escuchando.mp4", 10, 10, (60, None)),   # descarta transicion inicial
    "hablando":   ("Hablando.mp4",   12, 10, (0, None)),
    "procesando": ("Procesando.mp4", 12, 10, (15, None)),   # descarta 1er frame de escala distinta
}


def color_de_fondo(frame_bgr: np.ndarray) -> np.ndarray:
    """Toma el color dominante de las 4 esquinas (10x10px cada una) como
    referencia del fondo real de ESTE frame (el gradiente varia un poco
    entre frames, mejor no asumir un solo valor fijo)."""
    h, w = frame_bgr.shape[:2]
    esquinas = np.concatenate([
        frame_bgr[0:10, 0:10].reshape(-1, 3),
        frame_bgr[0:10, w - 10:w].reshape(-1, 3),
        frame_bgr[h - 10:h, 0:10].reshape(-1, 3),
        frame_bgr[h - 10:h, w - 10:w].reshape(-1, 3),
    ])
    return np.median(esquinas, axis=0)


def mascara_personaje(frame_bgr: np.ndarray, fondo_bgr: np.ndarray) -> np.ndarray:
    """True = personaje, False = fondo. Discrimina por SATURACION en HSV,
    no por distancia de color RGB: el fondo (magenta, con gradiente de
    brillo) tiene saturacion consistentemente alta sin importar cuan
    oscuro/claro este ese punto del gradiente (medido: S~218-221 en
    esquinas Y en el centro brillante), mientras el personaje es
    monocromatico blanco/negro/gris (S~0-30, sin importar el brillo).
    Robusto ante el gradiente Y evita el problema de floodFill: un
    flood-fill de tolerancia baja se filtraba ("puenteaba") a traves de
    zonas de sombreado gris del propio arte y borraba partes del
    personaje; uno de tolerancia alta se comia el fondo entero como si
    fuera personaje. La saturacion no tiene ese problema porque compara
    una propiedad que separa limpio blanco/negro/gris de magenta, sin
    importar el brillo absoluto de cada pixel."""
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    saturacion = hsv[:, :, 1]
    # Umbral alto (150, medido fondo real ~218-221) para que el ruido de
    # compresion H.264 en el sombreado oscuro del personaje (saturacion
    # moderada por artefactos de croma) no se cuele como "fondo" -- con
    # 100 quedaban motas magenta dispersas dentro del personaje.
    valor = hsv[:, :, 2]
    # La pupila negra (RGB~0,0,0) rompia esto: en HSV, S=(max-min)/max se
    # vuelve NUMERICAMENTE INESTABLE cuando V (brillo) es casi 0 -- una
    # division por un numero chico amplifica cualquier ruido de compresion
    # H.264 entre canales B/G/R, dando saturacion ALTA artificial en negro
    # puro (reproducido: el frame 99 daba magenta DENTRO de las pupilas).
    # El fondo real es magenta BRILLANTE (V~220 medido), asi que exigir
    # brillo alto ademas de saturacion alta descarta ese ruido sin afectar
    # el fondo real.
    es_fondo = (saturacion > 150) & (valor > 120)
    # Apertura morfologica: limpia motas de 1-2px sueltas (ruido) sin
    # comerse regiones grandes reales de fondo.
    kernel = np.ones((3, 3), np.uint8)
    es_fondo = cv2.morphologyEx(es_fondo.astype(np.uint8) * 255, cv2.MORPH_OPEN, kernel) > 0
    return ~es_fondo  # True = personaje


def recorte_cuadrado(mascara: np.ndarray, margen_frac: float = 0.06) -> tuple[int, int, int, int]:
    """Bounding box del personaje + margen, expandido a cuadrado.
    Clipeado SIEMPRE al tamano real del frame -- sin esto, un bounding box
    corrupto (visto antes con la deteccion global) se pasaba de largo y
    numpy lo truncaba en silencio al indexar, devolviendo el frame entero
    sin recortar en vez de fallar ruidoso.

    No filtra por componente conectado a proposito: 'procesando' tiene un
    globo de pensamiento flotando SEPARADO del cuerpo (parte deseada del
    diseño) que un filtro "solo el blob mas grande" descartaria como si
    fuera ruido. El bug real de 'escuchando' (fondo magenta sin recortar
    en el GIF final) resulto ser la paleta compartida de `armar_gif`, no
    la deteccion de mascara -- el filtro HSV de `mascara_personaje` ya da
    una mascara limpia sin blobs sueltos por su cuenta."""
    h, w = mascara.shape[:2]
    ys, xs = np.where(mascara)
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    alto, ancho = y1 - y0, x1 - x0
    lado = int(max(alto, ancho) * (1 + margen_frac * 2))
    cy, cx = (y0 + y1) // 2, (x0 + x1) // 2
    y0n, y1n = cy - lado // 2, cy + lado // 2
    x0n, x1n = cx - lado // 2, cx + lado // 2
    return max(y0n, 0), min(y1n, h), max(x0n, 0), min(x1n, w)


def procesar_frame(frame_bgr: np.ndarray, caja: tuple[int, int, int, int]) -> Image.Image:
    """Color-key ANTES de recortar/reducir, sobre el frame ORIGINAL sin
    distorsionar -- el personaje de cuerpo entero ocupa casi toda la
    altura de estos videos verticales, asi que el recorte cuadrado
    resultante termina siendo casi tan grande como el frame; reducirlo
    directo a 200x200 aplasta el alto mucho mas que el ancho (factores de
    escala distintos por eje) y eso rompe un flood-fill sobre el gradiente
    ya distorsionado (medido: 46% del frame mal clasificado en la imagen
    chica pese a que el frame grande daba una mascara limpia). Haciendo el
    color-key sobre el frame grande (geometria real, sin distorsion) se
    evita el problema de raiz.

    El propio filtro LANCZOS reintroduce un halo de 1px al reducir (mezcla
    el magenta puro con el borde blanco) -- pero ahora el fondo YA es
    magenta uniforme, no gradiente, asi que limpiarlo despues es una simple
    comparacion de distancia de color GLOBAL (no floodFill: ya no hace
    falta seguir un gradiente que ya no existe).

    `caja` es SIEMPRE la misma para todos los frames de un mismo estado
    (calculada una vez sobre un frame de referencia) para que el encuadre
    no salte entre cuadros del loop."""
    fondo = color_de_fondo(frame_bgr)
    mask_personaje = mascara_personaje(frame_bgr, fondo)
    mask_u8 = mask_personaje.astype(np.uint8) * 255
    kernel = np.ones((3, 3), np.uint8)
    # Erosiona el personaje 2px hacia adentro -- se come el anillo de
    # pixeles de transicion real (antialiasing) entre personaje y fondo.
    mask_erosionada = cv2.erode(mask_u8, kernel, iterations=2) > 0

    grande = frame_bgr.copy()
    grande[~mask_erosionada] = (COLOR_CLAVE[2], COLOR_CLAVE[1], COLOR_CLAVE[0])  # BGR

    y0, y1, x0, x1 = caja
    recortado = grande[y0:y1, x0:x1]
    rgb = cv2.cvtColor(recortado, cv2.COLOR_BGR2RGB)
    chico = np.array(Image.fromarray(rgb).resize((TAMANO_FINAL, TAMANO_FINAL), Image.LANCZOS))

    # Limpieza final: el fondo ya es magenta plano (sin gradiente), asi que
    # una comparacion de distancia GLOBAL alcanza para el halo que dejo
    # LANCZOS -- no hace falta floodFill de nuevo.
    dist = np.linalg.norm(chico.astype(np.float32) - np.array(COLOR_CLAVE, dtype=np.float32), axis=2)
    es_fondo_final = dist < 40
    chico[es_fondo_final] = COLOR_CLAVE
    return Image.fromarray(chico)


def armar_gif(frames_rgb: list[Image.Image], ruta_salida: str, fps: int) -> None:
    """GIF con transparencia REAL (1-bit) en el color clave -- no un GIF
    con fondo magenta visible. tkinter lee esto nativo (ver investigacion
    13.4).

    BUG que costo horas: cuantizar cada frame por separado (cada uno con
    su propia paleta MEDIANCUT) hace que el color clave caiga en un INDICE
    DE PALETA DISTINTO en cada frame -- pero el formato GIF (y el `save`
    de Pillow con `save_all`) solo acepta UN indice de transparencia
    global para todo el archivo. El resultado: el frame usado para elegir
    ese indice (el primero) se veia transparente, y el resto mostraba
    magenta solido sin recortar, porque el indice fijo apuntaba a otro
    color en SU paleta. Solucion: una unica paleta COMPARTIDA para todos
    los frames, con el color clave forzado siempre en el indice 0."""
    duracion_ms = int(1000 / fps)

    # Paleta compartida: cuantiza el frame con MAS colores distintos entre
    # todos (mejor cobertura de la paleta real del personaje) y la reusa
    # para el resto -- evita que cada frame elija tonos ligeramente
    # distintos para las mismas zonas (blanco del craneo, negro del
    # hoodie), lo que ademas reduce parpadeo de color entre cuadros.
    paletista = frames_rgb[0].convert("RGB").quantize(colors=255, method=Image.MEDIANCUT)
    paleta = paletista.getpalette()
    # Fuerza el color clave en el indice 0 exacto, corriendo lo que ya
    # estuviera ahi al final de la paleta.
    paleta = list(COLOR_CLAVE) + paleta[3:768]
    paletista.putpalette(paleta)

    cuadros_p = []
    for img in frames_rgb:
        rgb_arr = np.array(img.convert("RGB"))
        es_clave = np.all(rgb_arr == np.array(COLOR_CLAVE), axis=-1)
        p = img.convert("RGB").quantize(palette=paletista, dither=Image.NONE)
        arr = np.array(p)
        arr[es_clave] = 0  # fuerza el indice 0 (color clave) donde corresponde
        p = Image.fromarray(arr, mode="P")
        p.putpalette(paleta)
        cuadros_p.append(p)

    cuadros_p[0].save(
        ruta_salida, save_all=True, append_images=cuadros_p[1:], duration=duracion_ms,
        loop=0, transparency=0, disposal=2, optimize=False,
    )


def main() -> None:
    import os
    os.makedirs(CARPETA_DESTINO, exist_ok=True)

    for estado, (archivo, fps, n_frames_gif, (ini, fin)) in ESTADOS.items():
        ruta = f"{CARPETA_ORIGEN}\\{archivo}"
        cap = cv2.VideoCapture(ruta)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fin_real = fin if fin is not None else total - 1
        idxs = np.linspace(ini, fin_real, n_frames_gif, dtype=int)

        # Caja de recorte fija: se calcula UNA VEZ sobre el frame del medio
        # del rango estable (no el primero -- en 'escuchando'/'procesando'
        # el primer frame es justo el que tiene transicion/escala rara) y
        # se reusa para todos los frames de este estado.
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idxs[len(idxs) // 2]))
        ok, frame_ref = cap.read()
        fondo_ref = color_de_fondo(frame_ref)
        mask_ref = mascara_personaje(frame_ref, fondo_ref)
        caja = recorte_cuadrado(mask_ref)

        frames = []
        for i in idxs:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
            ok, frame = cap.read()
            if not ok:
                continue
            frames.append(procesar_frame(frame, caja))
        cap.release()

        salida = f"{CARPETA_DESTINO}\\{estado}.gif"
        armar_gif(frames, salida, fps)
        print(f"{estado}: {len(frames)} cuadros -> {salida}")


if __name__ == "__main__":
    main()
