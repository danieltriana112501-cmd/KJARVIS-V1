# Fase 08 — Interfaz gráfica base (pywebview + Flask), estilo Watch Dogs 2

## Objetivo

Construir la ventana principal de la aplicación: `pywebview` mostrando una
página HTML/CSS/JS servida por un Flask local, con sidebar y modales de
Tareas / Recordatorios / Configuración, en estética monocromática blanco
sobre negro estilo cómic (referencia visual: interfaz de Watch Dogs 2 /
DedSec — trazo blanco grueso, textura halftone, tipografía monoespaciada).

## Contexto

Depende de las **Fases 01–05** (todo lo que hay que exponer en la UI ya
debe existir y funcionar por texto/consola antes de ponerle interfaz).
Referencia estructural (no visual — el HRZ usa un estilo cyan/oscuro
distinto al pedido acá) de qué paneles conviene tener, ya revisada en
diseño:
`JARVIS-HRZ proyecto para clonar o copiar inspirarse y mejorar/_internal/assets/interfaz.html`
— de ahí se toma la IDEA de estructura (sidebar de iconos + panel central +
modales de Tareas/Recordatorios/Config), NO el CSS ni los colores (esos se
definen desde cero en esta fase según la guía visual de abajo).

## Guía visual (Watch Dogs 2 / cómic blanco-negro)

Esta sección es la referencia de estilo que también usan las Fases 09 y 10
— cualquier cambio de paleta/tipografía debe hacerse acá y no reinventarse
en otras fases.

**Paleta (estrictamente monocromática, sin colores de acento):**

```
--bg:            #050505   (negro casi puro, fondo de toda la app)
--bg-panel:      #0d0d0d   (fondo de paneles/modales, ligeramente más claro)
--line:          #f5f5f5   (blanco hueso, todos los bordes y trazos)
--line-dim:      #9a9a9a   (blanco atenuado, texto secundario/deshabilitado)
--text:          #f5f5f5   (texto principal)
--text-dim:      #7a7a7a   (texto secundario)
--danger:        #f5f5f5   (NO usar rojo/verde para estados — incluso
                            "eliminar" o "alarma sonando" se resuelven con
                            contraste blanco/negro invertido o parpadeo,
                            no con color; esto es una decisión de estilo
                            deliberada del usuario, no un olvido)
```

**Única excepción de color en toda la interfaz:** el panel ASCII central
(Fase 09) usa un efecto glitch con aberración cromática roja/azul
(`text-shadow: 2px 0 0 red, -2px 0 0 blue`, ver
`plans/material/skull-illustration-source.tsx` y la sección
correspondiente de `plans/phase-09-ascii-panel.md`) — confirmado
explícitamente por el usuario, se ve mejor así. Ningún otro elemento de la
interfaz (sidebar, modales, botones, estados de error/alarma) usa color;
esa regla se mantiene intacta, la excepción es puntual y exclusiva del
panel ASCII.

**Tipografía:** monoespaciada en toda la interfaz (headers y cuerpo). Usar
una fuente de sistema para no depender de internet/CDN (la app debe andar
offline salvo por las llamadas a Gemini): pila
`font-family: 'Consolas', 'Courier New', monospace;`.

**Texturas y trazos (lo que da el look "cómic"):**

- Bordes de 2px sólidos blancos en botones/paneles/inputs, esquinas
  **sin redondear** (`border-radius: 0` en casi todo — el HRZ usa mucho
  `border-radius`, acá se invierte esa decisión a propósito).
- Textura halftone sutil de fondo: un `background-image` con
  `radial-gradient` repetido en patrón de puntos pequeños, opacidad baja
  (5–8%), sobre `--bg`. Implementarlo como una capa CSS reutilizable
  (`.halftone-bg`) aplicada al `body`.
- Líneas de "escaneo" (scanlines) sutiles: overlay con
  `repeating-linear-gradient` horizontal, muy baja opacidad, opcionalmente
  animado con un `translateY` lento en loop — efecto sutil, no debe
  dificultar la lectura del texto.
- Efecto "glitch" ocasional (no continuo): una clase `.glitch` aplicable a
  elementos de estado (ej. cuando cambia de "inactivo" a "escuchando") que
  dispare una animación corta (200–400ms) de desplazamiento de
  sub-capas de texto en blanco/negro — usarlo con moderación, solo en
  transiciones de estado, nunca en loop constante (sería molesto para uso
  diario).
- Botones: fondo `--bg`, borde blanco 2px, texto blanco, en hover invertir
  a fondo blanco/texto negro (`filter` o cambio directo de
  `background`/`color`) — el clásico contraste invertido cómic/hacker.

**Referencia de mood, no de implementación literal:** pensar en las
pantallas de hackeo de Watch Dogs 2 (ScoutX, Nudle, perfil DedSec) — trazo
grueso, iconografía simple lineal (no rellena), MAYÚSCULAS en headers con
letter-spacing amplio, cero gradientes de color, cero sombras de color
(solo sombras blancas/negras si hace falta profundidad).

## Alcance de esta fase

### 1. Backend Flask local

Crear `Jarvis/app/server.py`:

- Flask bindeado a `127.0.0.1` (nunca `0.0.0.0` — regla de seguridad del
  proyecto, ver `plans/README.md`), puerto configurable (default algo como
  `5577`, evitar puertos comunes).
- Endpoints REST mínimos para que el frontend JS pueda:
  - `GET /api/tareas` / `POST /api/tareas` (list/add/complete/delete —
    reusa el módulo `tareas.py` de la Fase 02).
  - `GET /api/recordatorios` / `POST /api/recordatorios` (idem, Fase 03).
  - `GET /api/config` / `POST /api/config` (lee/escribe
    `Jarvis/app/config.py` de la Fase 01 — acá vive el campo de API key y
    el selector de voz).
  - `POST /api/mensaje` (recibe texto del chat de texto opcional, lo pasa
    a `GeminiAgent.procesar`, Fase 05, devuelve la respuesta).

### 2. Ventana pywebview

Crear `Jarvis/app/ui.py`:

- Levanta el Flask de `server.py` en un thread aparte.
- Abre una ventana `webview.create_window(...)` apuntando a
  `http://127.0.0.1:<puerto>/`, tamaño razonable (ej. 1000x700),
  redimensionable, con el ícono del proyecto si existe uno.

### 3. Frontend

Crear en `Jarvis/assets/` (carpeta ya creada vacía en la Fase 01):
- `index.html`
- `style.css` (implementa la guía visual de arriba)
- `app.js`

Estructura de la página (simplificada respecto al HRZ, sin Telegram,
Google Tools, GitHub, Noticias, ni mapa mundial — el usuario no pidió
esas cosas):

- **Sidebar** (iconos verticales, estilo lineal blanco): Tareas,
  Recordatorios, Configuración. Nada más por ahora.
- **Panel central**: por ahora, mientras no existe la Fase 09 (animación
  ASCII), mostrar simplemente un texto de estado grande centrado
  ("INACTIVO" / "ESCUCHANDO" / "HABLANDO" / "PROCESANDO") con la
  tipografía monoespaciada y un borde blanco simple alrededor — esto se
  reemplaza visualmente en la Fase 09, no antes.
- **Modal de Tareas**: tabs "Crear" / "Mis tareas" (mismo concepto que el
  HRZ, ver referencia de estructura arriba, pero con el estilo visual
  nuevo) — descripción + fecha + hora, lista ordenada por fecha próxima
  con checkbox para completar.
- **Modal de Recordatorios**: tabs "Nuevo" / "Mis recordatorios" — mensaje
  + fecha + hora + repetición (una vez/diario/semanal/días específicos) +
  campo opcional de instrucción para alarmas.
- **Modal de Configuración**: campo de API key de Gemini (input
  `type=password` con botón mostrar/ocultar), selector de voz (dropdown
  con las 8 voces de `VOCES_DISPONIBLES`), selector de dispositivo de
  mic/altavoz (poblar con `navigator.mediaDevices.enumerateDevices()` en
  JS), campo de ubicación (texto libre, ciudad), campo de hora de morning
  brief (input `type=time`, vacío = desactivado).

### 4. Botón de encendido/apagado de voz

En el header o cerca del panel central: un botón visible que
inicia/detiene la sesión de voz (`VoiceEngine.iniciar_sesion()` /
`detener_sesion()` de la Fase 06) — recordar que la sesión de voz es bajo
demanda, este botón es precisamente ese "demanda".

## Fuera de alcance

- No implementar todavía el panel ASCII animado (Fase 09) ni la ventana
  flotante PIP (Fase 10) — el panel central en esta fase es solo texto de
  estado simple.
- No agregar Telegram, clima en UI (opcional, se puede dejar para después
  si el usuario lo pide — el módulo de clima de la Fase 07 puede
  consumirse solo por voz por ahora sin necesidad de un modal dedicado).

## Verificación

Manual (es una interfaz gráfica, no automatizable sin un navegador
real controlado):

1. Levantar la app, confirmar que la ventana abre y carga sin errores de
   consola (revisar devtools de pywebview si están habilitados en modo
   debug).
2. Crear una tarea desde el modal, confirmar que aparece en
   `Jarvis/datos/tareas.json`.
3. Crear un recordatorio, confirmar en `Jarvis/datos/recordatorios.json`
   o `alarmas.json` según corresponda.
4. Guardar una API key y una voz en Configuración, cerrar y reabrir la
   app, confirmar que los valores persistieron (leyendo
   `Jarvis/datos/settings.json`).
5. Confirmar visualmente que la estética coincide con la guía (negro,
   blanco, sin colores de acento, bordes rectos, tipografía monoespaciada).

## Entregable final de la fase

- `Jarvis/app/server.py`, `Jarvis/app/ui.py` funcionando.
- `Jarvis/assets/index.html`, `style.css`, `app.js` implementando la guía
  visual y los 3 modales + sidebar recortada.
- Verificación manual completa realizada.
- Marcar `- [x] Fase 08` en `plans/README.md`.
