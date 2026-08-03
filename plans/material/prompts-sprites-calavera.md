# Prompts — sprites de la calavera (4 estados imprescindibles)

Ver `plans/INVESTIGACION-2026-07-27-voz-tools-ui.md` sección 13 (por qué
sprites 2D en vez de ASCII, por qué GIF, por qué bordes duros) y
`.claude/agents/jarvis-ui-builder.md` (paleta oficial del proyecto). Estos
prompts generan la **pose base** de cada estado — no el GIF animado
completo. Un generador de imágenes produce imágenes parecidas entre sí, no
cuadros consistentes de una misma animación (ver investigación 13.7,
opción 2). El flujo real es:

1. Generar la pose base de cada estado con estos prompts (4 imágenes).
2. Llevar cada pose base a Aseprite/Piskel y animarla a mano con 2-4
   variaciones simples encima (mandíbula, parpadeo, inclinación) — la IA da
   el diseño, el editor de sprites da el movimiento. Intentar que la IA
   genere el GIF de 8-12 cuadros directo da cuadros que no van a calzar
   entre sí.

## Regla no negociable en TODOS los prompts: bordes duros

La transparencia de la ventana del overlay es por color clave (binaria: un
píxel es 100% visible o 100% invisible). Un borde con antialiasing/blur deja
un halo fantasma alrededor del sprite. Por eso cada prompt de abajo pide
explícitamente **sin antialiasing, sin sombras difuminadas, sin glow, sin
gradientes** — no es una preferencia estética nada más, es un requisito
técnico. Si el resultado que da el generador tiene bordes suaves, hay que
re-generar insistiendo en esto o umbralizar la imagen a blanco/negro puro
después (cualquier editor lo hace en un paso).

## Paleta y fondo

- Trazo: blanco casi puro (`#f5f5f5`), grueso, tipo cómic/stencil.
- Fondo: **magenta sólido plano** `#FF00FE` — es el `color_clave` por
  defecto del paquete de personaje (`plans/INVESTIGACION...` sección 13.6),
  un color que no debe aparecer en el arte para poder recortarlo limpio
  después. Si el generador no logra un magenta parejo (gradiente, textura),
  también sirve fondo **negro sólido puro** `#000000` — se invierte o se
  recorta por umbral en cualquier editor, es más fácil de pedirle a un
  generador de imágenes que un magenta exacto.
- Nada de rojo/verde/azul en el personaje en sí (el proyecto reserva color
  únicamente para un efecto CSS de aberración cromática en la UI, no en el
  arte del sprite).
- Formato pedido: cuadrado, encuadre centrado, espacio de sobra alrededor
  (el sprite final va a 200×200px, mejor generar más grande y reducir).

## Prompt de estilo (repetir/adjuntar en los 4 de abajo)

```
2D game sprite, single character icon, centered, square composition, thick
bold black-and-white comic-book ink outline, flat cel-shaded, high contrast,
NO gradients, NO soft shadows, NO glow, NO anti-aliasing, NO blur, hard
sharp edges only, stencil-art style like Watch Dogs 2 UI iconography,
minimalist skull character, solid flat magenta background (#FF00FE), no
background texture, no scene, no floor, no environment
```

---

## 1. `inactivo` — respira, parpadea, mira alrededor

```
[PROMPT DE ESTILO] + a simple cartoon skull character standing neutral,
calm relaxed posture, one eye slightly closed mid-blink, head tilted very
slightly, mouth closed in a flat neutral line, idle resting pose, no
expression of urgency, front-facing three-quarter angle
```

## 2. `escuchando` — atenta, inclinada hacia adelante

```
[PROMPT DE ESTILO] + a simple cartoon skull character leaning forward
attentively, head tilted toward viewer as if listening closely, both eye
sockets wide open and alert, subtle antenna or ear-like spikes on top of
the skull pointed upward, alert focused posture, mouth closed
```

## 3. `hablando` — mandíbula en movimiento

```
[PROMPT DE ESTILO] + a simple cartoon skull character with jaw open mid-
speech, mouth open as if talking or shouting, energetic posture, slight
forward lean, eyes wide, dynamic mid-motion pose, jaw clearly separated
from the upper skull so it reads as an open/closed hinge for animation
```

## 4. `procesando` — pensando, gira, engranajes

```
[PROMPT DE ESTILO] + a simple cartoon skull character in a thinking pose,
head tilted to one side, one eye socket showing a small gear/cog symbol
instead of a normal eye, spiral or swirl symbol floating above the head,
static contemplative posture, mouth closed in a small flat line
```

---

## Después de generar

1. Revisar cada imagen contra la regla de bordes duros (sección de arriba)
   antes de aceptarla — es el paso que más arruina el resultado si se
   saltea.
2. Recortar a cuadrado, reducir a ~200×200px.
3. Si el fondo no salió magenta/negro sólido perfecto, umbralizar
   (cualquier editor: "reemplazar por color exacto por debajo de tolerancia
   X") antes de usarlo como color clave en `tkinter`.
4. Llevar las 4 poses base a Aseprite/Piskel, armar 2-4 cuadros de
   variación por estado (parpadeo para `inactivo`, mandíbula abriendo/
   cerrando para `hablando`, etc.) y exportar como GIF — ver el formato del
   paquete de personaje en `plans/INVESTIGACION-2026-07-27-voz-tools-ui.md`
   sección 13.6.
