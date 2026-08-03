# Fase 20 — Una figura distinta por estado (sistema de solo puntos)

## Objetivo

Hoy el overlay (`app/plexus.py`, Fase 19) muestra **siempre la misma esfera**
y solo cambia el color según el estado. El pedido es que además cambie de
**figura**. Esta fase reemplaza el sistema de partículas por uno de solo
puntos densos, donde cada estado tiene una geometría propia y reconocible.

## Contexto

Depende de **Fase 19** (`app/overlay.py`, `app/plexus.py`). No toca
`voice_engine.py`, `gemini_agent.py` ni el servidor Flask — el overlay
sigue siendo un cliente tonto que hace polling de `/api/estado`.

Todas las decisiones de abajo salen de mediciones, no de preferencia:
`plans/INVESTIGACION-2026-08-02-sistema-particulas.md`. Los dos hallazgos
que mandan:

- **§8.1** — El plexus paga O(N²) por las líneas y eso lo topa en ~140
  puntos. Sin líneas el costo es O(N): **4000 puntos salen más baratos que
  90 con plexus** (0.49 ms vs 1.16 ms).
- **§8.2** — Con 90 puntos y sin líneas *no hay figura* (se ven puntos
  sueltos). Hacen falta 400+ para que una forma se lea. Por eso no se puede
  simplemente "sacar las líneas" del sistema actual: hay que subir la
  densidad en el mismo movimiento.

## Alcance de esta fase

### 1. Catálogo de figuras (`app/figuras.py`, nuevo)

Un módulo con una función por figura, cada una devolviendo una nube de
puntos `(N, 3)` normalizada al cubo unitario:

| Función | Estado | Por qué esa figura |
|---|---|---|
| `esfera(n)` | `inactivo` | neutra, en reposo |
| `toro(n)` | `escuchando` | se abre hacia afuera, receptivo; el agujero la hace inconfundible |
| `esfera_onda(n, fase)` | `hablando` | superficie vibrando = emisión. `fase` avanza con el tiempo → la onda viaja |
| `dos_anillos(n)` | `procesando` | giroscopio: lee como maquinaria trabajando |

Reglas que el módulo debe respetar (medidas en la investigación, §4 y §8.5):

- **Figuras de curva antes que de superficie.** Con puntos fijos, una curva
  1D los concentra y queda densa; una superficie 2D los dispersa.
- **Nada de superformas de Gielis.** Refutadas dos veces, con dos sistemas
  distintos y a 40× la densidad (§3 y §8.5). No reintentar.
- Muestreo parejo: para superficies paramétricas, grilla densa +
  submuestreo aleatorio alcanza; no hace falta farthest-point sampling
  (probado: no aporta a esta escala).

### 2. Render de solo puntos (`app/plexus.py`, modificar)

- Sacar el cálculo de líneas (`_pares`, el bloque de Bresenham vectorizado)
  y su caché.
- Subir `N_PUNTOS` de 90 a **1200**.
- `frame()` pasa a recibir la nube de puntos ya construida, no solo la
  config: la geometría ahora depende del estado.
- Conservar tal cual: proyección en perspectiva, niveles de profundidad,
  `PISO_BRILLO`, rim lighting, y el color por estado.

**No tocar el contrato de bordes duros.** El `_check()` que verifica cero
píxeles en tono intermedio tiene que seguir pasando — es lo que evita el
halo del color-key (ver `INVESTIGACION-2026-08-01`, §1).

### 3. Morph entre figuras (`app/overlay.py`, modificar)

Al cambiar de estado hay que interpolar entre **dos nubes distintas**, no
solo entre colores. Requiere una correspondencia punto-a-punto.

Método validado (§5 de la investigación): ordenar ambas nubes por ángulo
esférico (φ redondeado, luego θ) y aparear por índice. Barato, y los
cuadros intermedios quedan coherentes.

Reusar el mecanismo de transición que ya existe (`cfg_desde`, `t_cambio`,
`DURACION_TRANSICION_S`, `mezclar_config`) — solo hay que sumarle la
interpolación de posiciones.

### 4. Calibración del tamaño de punto

Medido: `radio=0` cuesta 0.28 ms, `radio=1` cuesta 0.49 ms — los dos
sobran para 30 fps, así que la decisión es puramente estética.

Hallazgo visual a tener en cuenta: **el radio conviene por figura, no
global.** Con `radio=1` los anillos ganan presencia, pero la esfera y la
onda se empastan y pierden el aspecto de nube de puntos. Dejar el radio
como campo del catálogo de figuras, y calibrarlo mirando, no adivinando.

## Fuera de alcance

- **Atractores extraños** (Lorenz, Aizawa, etc.). Medidos y se ven bien,
  pero a 150 px leen como manchas caóticas más que como figuras con
  intención (§8.3). Reconsiderar solo si el overlay crece de tamaño.
- **Híbrido kNN** (puntos densos + pocas líneas). Es el que mejor se veía
  de todos, pero medido cuesta **7.3 ms/cuadro** a 400 puntos — 25× el
  sistema elegido, por el `argsort` completo de la matriz de distancias. Se
  podría rescatar con un k-d tree (`scipy.spatial.cKDTree`), pero eso suma
  dependencia y es una fase aparte con su propia medición.
- **Topología dinámica** (§2). Era la conclusión de la primera ronda de la
  investigación, pero queda sin efecto: sin líneas no hay topología.
- Animaciones de situación (Fase 22) y viñetas — siguen pendientes aparte.

## Verificación

1. `python -m app.plexus` — el self-check tiene que seguir dando `OK`,
   incluyendo el assert de **cero píxeles de halo** para cada figura nueva
   (hay que extenderlo a las 4, hoy recorre los 4 estados).
2. `python -m app.overlay --check` — geometría del dock y deriva intactas.
3. Medir el frame time real de las 4 figuras y dejarlo por escrito; el
   presupuesto es <2 ms para no pasar del ~6% de un núcleo a 30 fps.
4. En vivo, con el servidor real corriendo: iniciar y detener una sesión de
   voz y confirmar por captura que la figura **cambia** (no solo el color) y
   que el morph no da un salto brusco.
5. Confirmar sobre fondo oscuro Y claro que la figura se sigue leyendo
   (el rim lighting es lo que lo garantiza; es la queja que originó todo).
6. Verificar que la memoria del proceso queda estable tras varios minutos
   (la Fase 19 midió 6.3 MB estables; con 1200 puntos no debería cambiar,
   pero el `PhotoImage` por cuadro es el punto a vigilar).

## Entregable final de la fase

- `Jarvis/app/figuras.py` nuevo, con las 4 figuras y su `_check()`.
- `Jarvis/app/plexus.py` sin cálculo de líneas, `N_PUNTOS=1200`, `frame()`
  recibiendo la nube.
- `Jarvis/app/overlay.py` con morph de posiciones además de color.
- Números de rendimiento medidos anotados en el código o en este archivo.
- Marcar `- [x] Fase 20` en `plans/README.md`.

## Agregado durante la implementación (fuera del plan original)

**Atajo global Ctrl+Espacio para iniciar/detener la sesión de voz.** Pedido
en la misma sesión en que se implementó esta fase, se sumó acá en vez de
abrir una fase aparte por ser un cambio chico y en el mismo archivo
(`overlay.py`, que ya corre siempre en background).

Implementación: `overlay.py` hace polling de `GetAsyncKeyState(VK_CONTROL)`
y `GetAsyncKeyState(VK_SPACE)` cada 50 ms (mismo patrón que ya usa el
módulo para click-through dinámico) en vez de `RegisterHotKey` — evita
subclasear el `WndProc` de Tk, y funciona sin importar qué ventana tiene el
foco porque `GetAsyncKeyState` lee el estado físico del teclado. Dispara
solo en el flanco de subida (tecla recién apretada) para no alternar la
sesión de voz varias veces por segundo si se mantiene apretada.

Verificado en vivo: simulando la combinación con `keybd_event` (sin depender
de foco de ventana), `/api/voz/estado` cambió `false → true → false` en las
dos direcciones del toggle.

## Riesgos conocidos

- **La esfera y la onda pueden quedar demasiado parecidas.** Son las dos
  figuras "de superficie" del catálogo; si en vivo no se distinguen,
  exagerar la amplitud de la onda antes que cambiar de figura.
- **1200 puntos con `radio=1` puede verse como un blob sólido** y perder el
  aspecto de nube. Si pasa, bajar puntos en vez de subir radio.
- El morph entre figuras de topología muy distinta (esfera → dos anillos)
  es el caso más exigente; si se ve raro, la salida barata es acortar
  `DURACION_TRANSICION_S` para que el estado intermedio dure menos.
