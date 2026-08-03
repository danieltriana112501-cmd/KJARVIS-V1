# Investigación — Qué sistema de partículas sirve para lograr figuras por estado

**Fecha:** 2026-08-02

**Pregunta:** el overlay usa hoy una esfera de plexus (`app/plexus.py`). ¿Es
esa la mejor base para lograr **figuras distintas por estado**, o conviene
otro sistema de partículas?

**Alcance:** investigación con experimentos ejecutados en esta máquina.
Nada del repo modificado salvo este documento. Continúa
`plans/INVESTIGACION-2026-08-01-overlay-situaciones.md`.

---

## 0. Resumen ejecutivo

| # | Hallazgo | Confianza |
|---|---|---|
| 1 | **La topología de conexiones era el problema real, no la geometría.** Calcular las líneas una vez sobre la esfera y reusarlas en otra forma produce líneas que cruzan por el aire. Con topología **dinámica** (reconectar por cuadro según posiciones actuales) el toro y el nudo toroidal pasan de ilegibles a limpios. | Medido, comparación lado a lado |
| 2 | **La topología dinámica es barata**: 0.95 ms/cuadro a 90 puntos (vs 1.2 ms de la estática actual, porque la estática hace más líneas). Alcanza hasta ~140 puntos manteniendo >400 fps teóricos. No hay razón de rendimiento para no usarla. | Medido |
| 3 | **Las superformas (Gielis) son un callejón sin salida a esta escala.** Probé la hipótesis de que fallaban por mal muestreo y la **refuté**: con farthest-point sampling (reparto parejo garantizado sobre cualquier superficie) siguen ilegibles. A 90 puntos y 150 px no hay resolución suficiente para leer un cubo o una estrella. | Medido, hipótesis refutada |
| 4 | **Las formas basadas en CURVA leen mucho mejor que las basadas en superficie.** Nudo toroidal, anillo, doble anillo y espiral cónica se leen nítidos; cilindro y cubo-lattice se ven rotos o aburridos. Razón: una curva concentra todos los puntos en una línea 1D, así que la densidad por unidad de longitud es alta; una superficie 2D reparte los mismos 90 puntos en mucha más área. | Medido |
| 5 | **Morphear entre nubes distintas funciona** con una correspondencia por ángulo ordenado (barato). Los cuadros intermedios quedan coherentes, la malla no explota. | Medido |

> ⚠️ **Las secciones §1-§7 son la PRIMERA ronda, y se quedaron dentro de un
> solo paradigma** (nube de puntos + líneas por proximidad). La §8 mide
> sistemas genuinamente distintos y **revisa la recomendación de abajo** —
> leer §8 antes de decidir nada.

**Recomendación (primera ronda, revisada en §8.6):** quedarse con este
sistema de partículas (nube de puntos + plexus), cambiar la topología a
dinámica, y elegir las figuras entre las basadas en curva.

---

## 1. Qué se probó y qué se descartó sin probar

Sistemas de partículas considerados:

| Sistema | Veredicto |
|---|---|
| **Nube de puntos + plexus** (el actual) | **Elegido.** Ya funciona, barato, y los experimentos muestran que su límite era la topología, no el sistema en sí |
| Superformas de Gielis (una fórmula → muchas formas) | **Descartado por medición**, ver §3. Atractivo en teoría (morphing por interpolación de parámetros) pero ilegible a esta escala |
| Simulación con atractores (partículas que se mueven hacia una forma objetivo por fuerzas) | **No probado.** Daría el morph más orgánico, pero requiere integrador de física por cuadro y estado por partícula. Solo vale la pena si el morph por interpolación directa (§5, ya validado) se queda corto |
| Muestreo de SDF (funciones de distancia con signo) | **No probado.** Muy flexible para formas arbitrarias, pero el muestreo de superficie es caro y no aporta nada que las curvas paramétricas no den ya |

---

## 2. Hallazgo principal: topología estática vs dinámica

`plexus.py` calcula hoy los pares conectados **una sola vez** sobre la
esfera base y los reusa siempre. El comentario en el código lo justificaba
así: recalcular por cuadro haría que las líneas aparezcan y desaparezcan, y
eso se vería como ruido.

Eso es cierto **mientras la geometría sea una esfera**. Deja de serlo apenas
la forma cambia: los "vecinos" según la esfera dejan de estar cerca en la
forma nueva, y sus líneas cruzan el objeto por el aire.

Comparación medida (misma forma, mismos puntos, solo cambia la topología):

| Forma | Topología estática | Topología dinámica |
|---|---|---|
| Toro | malla cruzando el agujero, ilegible | **limpio**, el agujero se lee |
| Nudo toroidal | maraña total | **limpio**, se sigue la curva |
| Estrella (superforma) | ilegible | sigue ilegible (problema de la forma, no de la topología) |

Costo de reconectar por cuadro (distancia todos-contra-todos + render
completo):

```
 60 puntos:  0.59 ms/frame (1687 fps max,  129 líneas)
 90 puntos:  0.95 ms/frame (1048 fps max,  286 líneas)
140 puntos:  2.29 ms/frame ( 437 fps max,  606 líneas)
200 puntos:  4.41 ms/frame ( 227 fps max, 1444 líneas)
300 puntos:  9.71 ms/frame ( 103 fps max, 3201 líneas)
```

A los 30 fps del overlay, 90 puntos dinámicos cuestan ~3% de un núcleo.
**Es más barato que la implementación estática actual** (1.2 ms), porque la
estática con `dist_link=0.62` genera más líneas de las necesarias.

Efecto secundario que hay que aceptar: con topología dinámica las líneas
aparecen y desaparecen a medida que los puntos se mueven. En las capturas
no se ve como ruido sino como una malla viva — que es exactamente el
aspecto de los plexus "de verdad" (el plugin Plexus de After Effects,
particles.js). El miedo original era infundado **siempre que el movimiento
sea suave**; con un movimiento brusco sí parpadearía feo.

---

## 3. Hipótesis refutada: el muestreo no era el problema

Después del primer intento fallido con superformas, la hipótesis era que
fallaban por **cómo se muestrearon los puntos**: se tomaban los ángulos de
la esfera de Fibonacci y se modulaba el radio, lo que amontona puntos donde
el radio se achica.

Se implementó el fix correcto — muestreo denso del espacio paramétrico de la
forma + **farthest-point sampling** (elegir iterativamente el punto más
lejano a todos los ya elegidos; garantiza reparto parejo sobre *cualquier*
superficie, no solo la esfera) — y se comparó lado a lado con topología
dinámica en ambos para aislar la variable.

**Resultado: no hay mejora perceptible.** Cubo, estrella y flor siguen
ilegibles. La conclusión honesta es que el problema es de **presupuesto de
resolución**: 90 puntos en 150 px no alcanzan para que se lea una forma con
lóbulos y concavidades. La superformula necesita del orden de cientos de
puntos, y ahí el costo de la topología dinámica empieza a doler (§2).

Vale anotarlo para no volver a intentarlo: *el farthest-point sampling
funciona y está bien implementado; lo que no funciona es la superformula a
esta escala.*

---

## 4. Qué figuras leen bien (medido)

Todas con farthest-point sampling + topología dinámica, 90 puntos, 150 px:

| Figura | ¿Lee? | Nota |
|---|---|---|
| Esfera | ✅ | limpia y equilibrada, sigue siendo la mejor "neutra" |
| Toro | ✅ | el agujero se lee claro |
| Nudo toroidal (2,3) | ✅ | elegante, muy "HUD futurista" |
| Nudo toroidal (3,2) | ✅ | idem, más abierto |
| Anillo plano | ✅ | minimalista y muy nítido |
| **Dos anillos perpendiculares** | ✅ | parece un giroscopio/átomo. El más "premium tech" de todos |
| Espiral cónica | ✅ | se lee como vórtice |
| Cilindro | 🟡 | legible pero anodino |
| Doble hélice | ❌ | se ve como un cilindro grumoso, no se lee la hélice |
| Cubo lattice | ❌ | los puntos quedan tan separados en las aristas que se ve roto |
| Superformas (cubo/estrella/flor) | ❌ | ver §3 |

**Patrón claro:** las figuras de **curva** (nudo, anillo, espiral) ganan a
las de **superficie** (cilindro, cubo, superformas). Con un presupuesto fijo
de puntos, una curva 1D los concentra y queda densa; una superficie 2D los
dispersa y queda rala.

---

## 5. Morphing entre figuras distintas

Para interpolar entre dos nubes distintas hace falta una **correspondencia**
(qué punto de A va a qué punto de B). Se probó la opción barata: ordenar
ambas nubes por ángulo esférico (φ redondeado, luego θ) y aparear por
índice.

Funciona: los cuadros intermedios (25 %, 50 %, 75 %) quedan coherentes, la
malla no explota ni se anuda. No hace falta transporte óptimo ni nada caro.

Detalle: con topología dinámica el morph es aún más robusto, porque las
conexiones se recalculan sobre las posiciones intermedias reales en vez de
arrastrar una topología que ya no corresponde a ninguna de las dos formas.

---

## 6. Propuesta concreta (no implementada)

Cambios a `app/plexus.py`:

1. **Topología dinámica** en vez de `_pares()` cacheado sobre la base.
   Bajar `dist_link` a ~0.55 para compensar (con reconexión real hacen falta
   menos líneas para que se lea la estructura).
2. **Un catálogo de figuras por estado**, todas generadas con
   `muestreo_lejano(nube_densa, N)` una sola vez al arrancar:

   | Estado | Figura sugerida | Por qué |
   |---|---|---|
   | `inactivo` | esfera | neutra, en reposo |
   | `escuchando` | anillo plano o toro | se "abre" hacia el usuario, receptivo |
   | `hablando` | esfera con onda viajera | superficie vibrando = emisión |
   | `procesando` | dos anillos perpendiculares girando | giroscopio = maquinaria trabajando |

3. **Morph por correspondencia de ángulo ordenado** al cambiar de estado,
   reusando el `mezclar_config` + `DURACION_TRANSICION_S` que ya existe.

Riesgo conocido a vigilar: con topología dinámica y morph simultáneo, si el
movimiento entre estados es muy rápido las líneas pueden parpadear. Mitigación:
mantener `DURACION_TRANSICION_S` en 0.6 s o más.

---

---

## 7. Fuentes

Todo lo de este documento es medición propia en esta máquina (scripts
descartables en el scratchpad de la sesión). Las técnicas usadas son
estándar y se pueden contrastar con:

- Farthest-point sampling — técnica clásica de muestreo de superficies
- Fórmula de Gielis (superformula) — generalización de la superelipse
- Nudos toroidales — curvas paramétricas `(p, q)` clásicas
- Efecto plexus con reconexión por cuadro — el modelo que usan
  [particles.js](https://github.com/VincentGarreau/particles.js) y el plugin
  Plexus de After Effects

---

## 8. Segunda ronda — comparar SISTEMAS distintos, no variantes del mismo

**Motivo:** la primera ronda (§1-§6) se quedó dentro del paradigma "nube de
puntos + líneas por proximidad". Los otros sistemas estaban listados en §1
como *no probados* — o sea, opinión, no medición. Esta ronda los mide.

### 8.1 Costo: la diferencia es estructural, no marginal

| Sistema | ms/cuadro | fps máx |
|---|---|---|
| Plexus, 90 puntos (el actual) | 1.16 | 868 |
| Solo puntos, 400 | **0.20** | 4923 |
| Solo puntos, 1500 | **0.30** | 3360 |
| Solo puntos, 4000 | **0.49** | 2045 |
| Wireframe real (icosaedro) | 0.35 | 2874 |
| Atractor Aizawa (2025 pts) | 0.35 | 2842 |

**El hallazgo que cambia el análisis:** el plexus paga un costo O(N²) por
calcular las líneas, y eso lo topa en ~90-140 puntos. Sin líneas, el costo
es O(N) y **4000 puntos salen más baratos que 90 con plexus**.

Eso importa porque en §3 se concluyó que las figuras complejas fallaban por
"presupuesto de resolución" (pocos puntos). Con un sistema sin líneas ese
presupuesto se multiplica por 40.

### 8.2 Cuántos puntos hace falta para que una figura "lea"

| Densidad | Resultado |
|---|---|
| 90 puntos, solo dots | ❌ se ve como puntos random, no hay forma |
| 400 puntos, solo dots | ✅ ya se lee la esfera |
| 1500 puntos, solo dots | ✅✅ nítida, aspecto "nube de puntos / holograma" |

O sea: **el plexus no es opcionalmente mejor a bajo N — es obligatorio**. Con
90 puntos y sin líneas no hay figura; las líneas son las que construyen la
forma. Son dos regímenes distintos, no dos estilos intercambiables.

### 8.3 Atractores extraños (Lorenz, Aizawa, Thomas, Halvorsen)

Sistema genuinamente distinto: no se define una superficie y se la muestrea,
sino que se **integra una ecuación diferencial** (RK4) y la trayectoria *es*
la figura.

- Cada atractor da una forma 3D inconfundible y distinta de las demás — que
  es exactamente lo que pedía el objetivo "una figura por estado".
- El aspecto es **orgánico y fluido**, muy distinto del look geométrico del
  plexus. Aizawa y Halvorsen son los más lindos.
- Costo bajo (0.35 ms): la trayectoria se integra **una sola vez** al
  arrancar; por cuadro solo se rota y proyecta.
- Contra: se ven algo caóticos/ruidosos a 150 px. Y no admiten morph
  trivial entre sí (habría que interpolar los parámetros de la ODE, y el
  camino intermedio pasa por atractores que pueden ser degenerados).

### 8.4 Wireframe real (aristas declaradas, no por distancia)

Aristas verdaderas de un poliedro en vez de "unir lo que esté cerca".
Limpio, geométrico, barato (0.35 ms), y **sin el problema de topología de
§2** porque las aristas son parte de la definición de la figura, no una
inferencia. Es la opción más "CAD/técnica" del conjunto.

### 8.5 Superformas: refutadas por segunda vez

Se reintentaron con el sistema de solo-puntos a 1500 puntos (40× la
resolución del intento anterior). **Siguen ilegibles**: quedan como manchas
ruidosas, mientras la esfera a la misma densidad se lee perfecta. Confirma
§3 desde un ángulo independiente. Cerrar el tema: las superformas de Gielis
no sirven para este overlay, y no es por falta de puntos ni por la topología.

### 8.6 Conclusión de la segunda ronda

No hay un ganador único: son **estéticas distintas con regímenes de costo
distintos**.

| Sistema | Estética | Densidad | Costo | Figuras distintas |
|---|---|---|---|---|
| Plexus | red / circuito | baja (≤140) | alto | limitado (topología, §2) |
| Solo puntos denso | holograma / nube | alta (400-4000) | muy bajo | cualquiera |
| Atractores | orgánico / fluido | media-alta | bajo | excelente, una por atractor |
| Wireframe real | geométrico / CAD | muy baja | muy bajo | buena |

**Recomendación revisada:** si el objetivo es *figuras claramente distintas
por estado*, el sistema de **solo puntos denso** es mejor base que el plexus
actual: cualquier figura funciona (no hay líneas que puedan cruzarse mal),
cuesta 4× menos, y el aspecto "nube de puntos" es más sobrio que la maraña
del plexus. El plexus conviene si se prioriza el look "red/circuito" por
encima de la variedad de figuras.

Opción intermedia no probada: **puntos densos + unas pocas líneas** (solo
las k conexiones más cortas por punto, O(N·k) en vez de O(N²)) — daría el
acento de red sin el costo ni la maraña. Es lo que probaría antes de decidir.
