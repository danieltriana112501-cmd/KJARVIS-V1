# Investigación — Overlay tkinter (Fase 19) y animaciones de situación (Fase 22)

**Fecha:** 2026-08-01

**Alcance:** SOLO investigación con spikes reales ejecutados en esta máquina
contra los assets ya generados (`Jarvis/assets/personajes/calavera/`) y el
servidor Flask real (no mocks). No se tocó código de la app — todos los
scripts viven en el scratchpad de la sesión. Continúa
`plans/INVESTIGACION-2026-07-27-voz-tools-ui.md` sección 10 (overlay,
arquitectura, sonidos, viñetas — sigue vigente, no se repite acá) y sección
13 (paquete de personaje con sprites, ya implementado).

---

## 0. Resumen ejecutivo

| # | Hallazgo | Confianza |
|---|---|---|
| 1 | El spike original (10.3) confirmaba que `-transparentcolor` "funciona" — cierto, pero con los assets REALES apareció un bug que ese spike genérico no exponía: si el `Label` de Tk arranca **sin** `image=` (vacío) y se le asigna una imagen recién en el primer tick de animación, la ventana entera queda **negra sólida** de forma permanente — ni transparente ni magenta. `.configure(image=...)` después ya no lo arregla. | Medido, reproducido y aislado con capturas de pantalla reales |
| 2 | Bug más grave: el patrón de click-through de la sección 10.6 (`GetWindowLongW` + `SetWindowLongW` con `WS_EX_TRANSPARENT`) **rompe el color-key** que Tk configuró internamente para `-transparentcolor` — la ventana vuelve a quedar negra sólida en cuanto se activa click-through. Hay que **re-aplicar `SetLayeredWindowAttributes` con `LWA_COLORKEY` explícito** después de tocar el estilo extendido. | Medido, reproducido y aislado |
| 3 | Con ambos fixes, el pipeline completo (DPI awareness + `overrideredirect` + `topmost` + `-transparentcolor` + click-through real + polling de `/api/estado` contra el servidor Flask real + cambio de animación) funciona de punta a punta — confirmado iniciando y deteniendo una sesión de voz real mientras el overlay corría: detectó `inactivo→escuchando→inactivo` correctamente. | Medido end-to-end, sin mocks |
| 4 | Pedir el HWND de la ventana (`winfo_id()`/`GetParent`) **antes** de `root.update_idletasks()` puede devolver un handle inválido (medido: `GetParent` dio `0`) — `SetWindowLongW` sobre un handle inválido no lanza excepción, falla en silencio. | Medido |
| 5 | Falta un mecanismo para que `/api/estado` (o un endpoint nuevo) avise al overlay cuando vence un recordatorio — ya lo marcaba la investigación anterior (7.4) como pendiente. Encontré el gancho exacto: `recordatorios._loop_runner`, justo donde llama a `_disparar(item, ...)`. | Confirmado leyendo el código actual |
| 6 | Para las animaciones de situación (Fase 22), el patrón técnico de "reproducir una vez y volver al estado normal" necesita que el overlay tenga una máquina de estados de 2 modos (`loop` vs `una_vez`) que **pause** la aplicación del polling normal mientras se reproduce una situación — si no, el polling puede pisar la animación a mitad de reproducción. | Diseño derivado, no implementado |

---

## 1. Overlay tkinter (Fase 19) — hallazgos empíricos con los assets reales

### 1.1 Bug #1 — el Label no puede arrancar vacío

Reproducido con capturas de pantalla reales (no simulado):

- Crear `tk.Label(root, bg=color_clave, bd=0)` **sin** `image=`, y asignar la imagen recién en el primer callback de animación (`label.configure(image=frames[0])`) → **la ventana entera se ve negra sólida**, sin importar si el `-transparentcolor` está bien configurado.
- El mismo `.configure(image=...)` para **cambiar** de una imagen a otra, una vez que el Label ya arrancó con una imagen válida desde su primer frame de vida, **funciona perfecto** (confirmado con captura: cambié de `frames[0]` a `frames[3]` a mitad de sesión y la transparencia se mantuvo intacta).

**Regla para la implementación real:** cargar los frames del estado inicial (`inactivo`, o lo que devuelva `/api/estado` en el primer poll síncrono) **antes** de construir el `Label`, y pasarlos directo al constructor:

```python
frames_iniciales = cargar_frames("inactivo")
label = tk.Label(root, image=frames_iniciales[0], bg=color_clave, bd=0)
label.image = frames_iniciales[0]  # referencia fuerte, ver 10.3 de la investigacion anterior
label.pack()
```

### 1.2 Bug #2 — click-through rompe el color-key (el más importante)

El patrón de la investigación anterior (10.3, verificado con un spike genérico) era:

```python
hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
estilo = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, estilo | WS_EX_LAYERED | WS_EX_TRANSPARENT)
```

Con los assets reales, este patrón **deja la ventana negra sólida** — confirmado quitando solo este bloque (todo lo demás igual) y viendo que la calavera vuelve a aparecer con transparencia perfecta. La causa: `-transparentcolor` de Tk configura internamente la ventana como *layered* con un color-key vía `SetLayeredWindowAttributes(..., LWA_COLORKEY)`. Tocar el estilo extendido con `SetWindowLongW` después de eso pisa ese estado interno.

**Fix confirmado — re-aplicar el color-key explícito después de activar click-through:**

```python
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x80000
WS_EX_TRANSPARENT = 0x20
LWA_COLORKEY = 0x1

hwnd = root.winfo_id()  # ver 1.3 — llamar DESPUES de update_idletasks()
estilo_previo = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, estilo_previo | WS_EX_LAYERED | WS_EX_TRANSPARENT)

# Sin esto, la ventana queda negra: hay que decirle a Windows CUAL es el
# color-key otra vez, porque tocar el estilo extendido lo resetea.
r, g, b = root.winfo_rgb(color_clave)          # 16-bit por canal
r8, g8, b8 = r >> 8, g >> 8, b >> 8              # a 8-bit por canal
colorref = (b8 << 16) | (g8 << 8) | r8           # COLORREF de Windows: 0x00BBGGRR
ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, colorref, 0, LWA_COLORKEY)
```

Verificado leyendo el estilo de vuelta (`GetWindowLongW` después de `SetWindowLongW`) en vez de asumir que la llamada tuvo efecto — con esto se confirmó el bit `WS_EX_TRANSPARENT` puesto de verdad, no solo que la llamada no tiró error.

Esto también resuelve, de paso, el requisito de la sección 10.6 de la investigación anterior ("click-through es un interruptor, no un estado fijo" — se prende y apaga según si el mouse está encima): cada vez que se prenda/apague el click-through dinámicamente, hay que **repetir este mismo patrón completo** (tocar el estilo Y re-aplicar el color-key), no solo tocar el estilo.

### 1.3 Bug #3 (menor) — pedir el HWND antes de tiempo

```python
hwnd = ctypes.windll.user32.GetParent(root.winfo_id())  # sin update_idletasks antes: dio 0
```

`root.winfo_id()` puede devolver un ID válido de Tk incluso si la ventana real de Windows todavía no está completamente materializada por el sistema operativo. Llamar `root.update_idletasks()` antes de tocar el HWND con `ctypes` evita operar sobre un handle inválido — y como `SetWindowLongW`/`SetLayeredWindowAttributes` no lanzan excepción Python sobre un HWND inválido, el fallo es **silencioso** si no se verifica.

**Regla:** siempre `root.update_idletasks()` antes de cualquier llamada `ctypes` sobre la ventana, y siempre releer el valor con `Get*` después de un `Set*` para confirmar que se aplicó, en vez de confiar en que la llamada no tiró excepción.

### 1.4 Confirmación end-to-end con datos reales (no mocks)

Con los dos fixes de arriba aplicados, corrí el overlay completo (DPI awareness, `overrideredirect`, `topmost`, `-transparentcolor`, click-through, polling real cada 500ms) contra el servidor Flask real (`app.server:app`, puerto 5577) mientras iniciaba y detenía una sesión de voz real (`POST /api/voz/iniciar` / `/detener`):

```
[overlay] estado -> escuchando (10 frames, 10fps)
[overlay] estado -> inactivo (10 frames, 8fps)
```

El overlay detectó ambos cambios de estado en tiempo real, cargó el GIF correcto para cada uno (con su fps propio leído de `personaje.json`), y no lanzó ninguna excepción en toda la sesión. Esto confirma que la arquitectura "overlay = cliente tonto que hace polling" (10.5 de la investigación anterior) funciona en la práctica, no solo en el papel.

### 1.5 Patrón completo verificado (para copiar al implementar)

```python
import ctypes, json, tkinter as tk, urllib.request
from pathlib import Path

CARPETA_PERSONAJE = Path(".../Jarvis/assets/personajes/calavera")
API_ESTADO = "http://127.0.0.1:5577/api/estado"

ctypes.windll.shcore.SetProcessDpiAwareness(1)  # ANTES de crear cualquier Tk()

personaje = json.loads((CARPETA_PERSONAJE / "personaje.json").read_text(encoding="utf-8"))
color_clave = personaje["color_clave"]

root = tk.Tk()
root.overrideredirect(True)
root.geometry(f"{personaje['tamano'][0]}x{personaje['tamano'][1]}+200+200")
root.configure(bg=color_clave)
root.wm_attributes("-transparentcolor", color_clave)
root.wm_attributes("-topmost", True)

cache_frames = {}
def cargar_frames(estado_nombre):
    if estado_nombre in cache_frames:
        return cache_frames[estado_nombre]
    ruta = CARPETA_PERSONAJE / personaje["estados"][estado_nombre]["gif"]
    frames = []
    i = 0
    while True:
        try:
            frames.append(tk.PhotoImage(file=str(ruta), format=f"gif -index {i}"))
        except tk.TclError:
            break
        i += 1
    cache_frames[estado_nombre] = frames
    return frames

# Label NUNCA vacio -- ver 1.1
frames_iniciales = cargar_frames("inactivo")
label = tk.Label(root, image=frames_iniciales[0], bg=color_clave, bd=0)
label.image = frames_iniciales[0]
label.pack()
estado_actual = {"nombre": "inactivo", "frame_idx": 1, "frames": frames_iniciales,
                  "fps": personaje["estados"]["inactivo"]["fps"]}

root.update_idletasks()  # ver 1.3, antes de tocar el hwnd

# click-through -- ver 1.2, los dos pasos son obligatorios juntos
GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TRANSPARENT, LWA_COLORKEY = -20, 0x80000, 0x20, 0x1
hwnd = root.winfo_id()
estilo = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, estilo | WS_EX_LAYERED | WS_EX_TRANSPARENT)
r, g, b = root.winfo_rgb(color_clave)
colorref = ((b >> 8) << 16) | ((g >> 8) << 8) | (r >> 8)
ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, colorref, 0, LWA_COLORKEY)

def poll_estado():
    try:
        with urllib.request.urlopen(API_ESTADO, timeout=1) as resp:
            nuevo = json.loads(resp.read()).get("estado", "inactivo")
        if nuevo not in personaje["estados"]:
            nuevo = "inactivo"  # regla: si falta la animacion, cae a inactivo
        if nuevo != estado_actual["nombre"]:
            estado_actual.update(nombre=nuevo, frames=cargar_frames(nuevo),
                                  fps=personaje["estados"][nuevo]["fps"], frame_idx=0)
    except Exception:
        pass
    root.after(500, poll_estado)

def animar():
    frames = estado_actual["frames"]
    idx = estado_actual["frame_idx"] % len(frames)
    label.configure(image=frames[idx])
    label.image = frames[idx]
    estado_actual["frame_idx"] += 1
    root.after(int(1000 / estado_actual["fps"]), animar)

poll_estado()
animar()
root.mainloop()
```

---

## 2. Animaciones de situación (Fase 22)

Catálogo ya definido en la investigación anterior (13.5, eje 2): aparece, se
va a dormir, aviso de recordatorio, burla, celebración, agarrado y
arrastrado, sorpresa, error. Acá va lo que faltaba: prompts concretos +
patrón técnico de reproducción.

### 2.1 De dónde sale el arte — ahora con referencia real

A diferencia de los 4 estados base (donde no existía todavía el personaje y
hubo que describirlo desde cero), ahora **sí existe un personaje real** con
diseño consistente ya fijado (el chico-calavera con hoodie negro, cadena,
zapatillas). Cualquier generador de imagen que soporte imagen de
referencia (image-to-image / character reference) debería recibir uno de
los frames ya extraídos como ancla, en vez de solo la descripción textual
de estilo — esto reduce mucho el riesgo de "deriva de diseño" que ya se
vio con Veo3 en la sesión anterior (el personaje cambiaba de rasgos entre
generaciones sin un ancla visual fuerte).

Frame de referencia sugerido: cualquier cuadro de `inactivo.gif` con el
personaje de cuerpo entero, de frente — es el más neutro para servir de
ancla a poses nuevas.

### 2.2 Prompts — pose base por situación (imagen)

Mismo bloque de estilo que `plans/material/prompts-sprites-calavera.md`,
más "same character as the reference image, do not redesign" (ver el
bloque de bloqueo de identidad ya usado en
`plans/material/prompts-veo3-animacion-calavera.md`):

```
[REFERENCIA: adjuntar un frame de inactivo.gif]
2D game sprite, single character icon, centered, square composition, thick
bold black-and-white comic-book ink outline, flat cel-shaded, high contrast,
NO gradients, NO soft shadows, NO glow, NO anti-aliasing, NO blur, hard
sharp edges only, solid flat magenta background (#FF00FE), no background
texture, no scene, no floor, no environment. Preserve the EXACT same
character design as the reference image -- same skull shape, same hoodie,
same sneakers, same chain, same proportions, do not redesign.
```

Con esa base, el detalle específico de cada situación:

| Situación | Detalle a agregar al prompt | Prioridad |
|---|---|---|
| Aparece / se despierta | `character emerging/rising into frame from below, eyes opening, slightly hunched then straightening up` | Alta |
| Se va a dormir | `character slouching down, eyes closing, arms going limp, sinking slightly` | Alta |
| Aviso de recordatorio | `character alert, pointing forward with one hand, mouth open as if shouting an announcement, urgent posture` | Alta |
| Burla / sarcasmo | `character with one eyebrow-ridge raised, arms crossed, smirking expression, judging posture` | Media |
| Celebración | `character with both arms raised up in victory, wide open-mouth grin, jumping pose` | Media |
| Agarrado y arrastrado | `character being dragged sideways, body tilted, one arm extended back as if being pulled, surprised expression` | Media |
| Sorpresa | `character with eye sockets wide open, jaw dropped open, body leaning back sharply` | Baja |
| Error / no entendí | `character with a confused expression, head tilted, one hand scratching the back of the head, question-mark symbol floating above` | Baja |

### 2.3 Prompts — animación Veo3 (I2V, one-shot, NO loop)

Diferencia clave con los 4 estados base: estas animaciones **no son loop**
— se reproducen una vez y terminan. El prompt de cámara/identidad es el
mismo bloque ya validado (`plans/material/prompts-veo3-animacion-calavera.md`),
pero **sin** pedir "seamless looping motion, first and last frame match
exactly" (eso era específico para loops) — acá se pide lo contrario:

```
Animate this skull character with locked static camera, no camera
movement, no pan, no zoom, no dolly, tripod shot. Preserve the exact same
character design throughout, same skull shape, same hoodie, same
proportions, same line thickness, do not redesign the character, character
must look identical to the input image in every frame except for the
described movement. [DETALLE DE LA SITUACION, ver tabla 2.2, versión de
acción en vez de pose estática -- ej. para "aparece": "the character rises
up into frame from below over the course of the clip and ends standing
upright, alert"]. Keep the exact same flat black and white comic ink art
style, hard sharp edges, no anti-aliasing, no blur, no added shadows, no
gradients, no new lighting, background stays solid flat magenta with zero
variation throughout. The clip should have a clear beginning and end
pose, NOT a loop. No audio, silent, no camera shake.
```

Post-proceso: igual que los 4 estados (extraer cuadros, mismo pipeline de
`plans/material/procesar_sprites_calavera.py` — reusable sin cambios,
solo hay que ajustar `ESTADOS` por una situación y no descartar frames de
"transición" ya que acá el principio Y el final son intencionales).

### 2.4 Patrón técnico: reproducir una vez y volver al estado normal

No estaba resuelto en la investigación anterior más allá de "se reproducen
una vez y vuelven al estado que corresponda". El punto que hay que resolver
en el diseño: el overlay tiene un loop de polling corriendo cada 500ms
(`poll_estado`) que normalmente pisa `estado_actual` apenas cambia — si una
situación se dispara mientras el polling sigue activo, un cambio de estado
real (ej. el usuario empieza a hablar) puede cortar la animación de
situación a la mitad.

**Diseño propuesto** (extiende el patrón de 1.5, no implementado):

```python
estado_actual = {"nombre": "inactivo", "modo": "loop", "frame_idx": 1,
                  "frames": frames_iniciales, "fps": 8}

def reproducir_situacion(nombre_situacion):
    """Interrumpe el loop normal, reproduce una animacion de situacion UNA
    vez, y al terminar vuelve a lo que /api/estado diga en ese momento."""
    frames = cargar_frames_situacion(nombre_situacion)  # carpeta 'situaciones', no 'estados'
    estado_actual.update(nombre=nombre_situacion, modo="una_vez",
                          frames=frames, frame_idx=0,
                          fps=personaje["situaciones"][nombre_situacion]["fps"])

def poll_estado():
    if estado_actual["modo"] == "una_vez":
        root.after(500, poll_estado)  # no tocar estado_actual mientras reproduce
        return
    # ... resto igual que 1.5 ...

def animar():
    frames = estado_actual["frames"]
    idx = estado_actual["frame_idx"]
    if estado_actual["modo"] == "una_vez" and idx >= len(frames):
        estado_actual["modo"] = "loop"  # termino: vuelve al polling normal
        estado_actual["nombre"] = None  # fuerza que el proximo poll recargue de verdad
        root.after(1, animar)
        return
    label.configure(image=frames[idx % len(frames)])
    label.image = frames[idx % len(frames)]
    estado_actual["frame_idx"] += 1
    root.after(int(1000 / estado_actual["fps"]), animar)
```

`reproducir_situacion()` se dispararía desde: un evento nuevo detectado en
el polling (ver 2.5, para "aviso de recordatorio"), o directamente desde un
handler de mouse en la ventana (click → "sorpresa", arrastre → "agarrado y
arrastrado" en `<B1-Motion>`), sin pasar por el servidor.

### 2.5 El gancho que falta para "aviso de recordatorio"

`/api/estado` hoy no sabe nada de recordatorios (7.4 de la investigación
anterior). Encontré el punto exacto donde engancharlo, leyendo el código
actual de `recordatorios.py`:

```python
def _loop_runner(tts_fn, player, agente=None):
    while True:
        ...
        for item in items:
            ...
            if dt <= ahora:
                print(f"[Recordatorios] DISPARANDO ...")
                _disparar(item, tts_fn, player, agente)   # <-- ACA
                ...
```

**Propuesta mínima:** un dict a nivel de módulo (mismo patrón que
`_estado_texto`/`_voz_cache` que ya existen en `server.py`) actualizado
justo antes o después de `_disparar(...)`:

```python
_ultimo_evento = {"tipo": None, "ts": 0.0}
# en _loop_runner, justo antes de _disparar(...):
_ultimo_evento_recordatorios["tipo"] = "recordatorio"
_ultimo_evento_recordatorios["mensaje"] = item.get("message")
_ultimo_evento_recordatorios["ts"] = time.time()
```

Y en `server.py`, agregar el timestamp del último evento a `/api/estado`
(o un endpoint nuevo `/api/eventos`) para que el overlay (que ya hace
polling cada 500ms) compare contra el último `ts` que vio y dispare
`reproducir_situacion("recordatorio")` cuando cambie — mismo patrón que ya
usa para detectar cambios de estado normal, solo que comparando un
timestamp en vez de un string.

---

## 3. Fuentes

- Todo lo de `plans/INVESTIGACION-2026-07-27-voz-tools-ui.md` sección 10
  (arquitectura, sonidos, viñetas) y 13 (paquete de personaje) sigue
  vigente — este documento solo agrega lo que un spike con assets reales
  reveló que el spike genérico anterior no exponía.
- Hallazgos de este documento: todos medidos en esta máquina con scripts
  descartables (scratchpad), nada tocado en el repo salvo este archivo.
