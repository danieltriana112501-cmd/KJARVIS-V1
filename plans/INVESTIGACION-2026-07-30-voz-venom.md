# Investigación — Voz de Venom (pitch real + capas) para `audio_fx.py`

**Fecha:** 2026-07-30

**Alcance:** SOLO investigación con mediciones empíricas reales sobre esta
máquina (instalé y probé librerías, no son solo lecturas de documentación).
No se tocó ninguna línea de `app/audio_fx.py` ni `app/voice_engine.py` en esta
sesión. Este documento es el insumo para implementar el efecto después.

---

## 0. Resumen ejecutivo

| # | Hallazgo | Confianza |
|---|---|---|
| 1 | El docstring actual de `audio_fx.py` (línea 1-11) descarta pitch-shift real por miedo a que introduzca "latencia creciente o cortes". **Es cierto para la librería obvia (`pedalboard`), pero NO para todas** — medí `pedalboard.PitchShift` (Rubber Band en modo *offline*) y sí acumula latencia sin techo: ~1 segundo de audio perdido/atrasado en los primeros 5s. Confirma la sospecha original, pero por la librería equivocada. | Medido en esta máquina |
| 2 | **`pylibrb`** (bindings directos a Rubber Band, no vía `pedalboard`) expone el modo `PROCESS_REALTIME` + engine rápido (`ENGINE_FASTER`) que la doc de Rubber Band dice que NO hace el padding/lookahead del modo offline. Medido: **latencia constante ~40ms, sin crecer en 30s simulados**, CPU ~1.2% del tiempo real. Esto SÍ es viable en el pipeline chunk-a-chunk actual. | Medido en esta máquina, robusto (30s) |
| 3 | `pylibrb` también expone `FORMANT_PRESERVED` — clave para que bajar el pitch mucho no suene "chipmunk al revés" (formantes de una persona chica en un tono grave), sino una voz grave que sigue sonando como una persona grande. | Doc oficial de Rubber Band + confirmado que la opción existe en el binding |
| 4 | Lo que Sony realmente hizo para Venom **no fue solo pitch-shift**: fue **layering** — la voz de Tom Hardy + una segunda voz (Brad Venable) + grabación de gruñidos/gaspidos propios de Hardy, mezclados y refinados en post. Un pitch-shift puro (por más real que sea) da una voz grave, no LA voz de Venom. | Fuentes de industria (ver Fuentes) |
| 5 | `pylibrb` es GPLv2 (envuelve Rubber Band, dual GPLv2/comercial). Para uso personal sin distribuir, no hay problema práctico. Si el proyecto se distribuyera como binario cerrado algún día, hay que revisarlo. | Doc del paquete |

**Recomendación de una línea:** pitch-down real vía `pylibrb` (no `pedalboard`) + mantener el `FiltroUltratumba` actual encima (ring-mod + saturación asimétrica + eco ya dan el "growl") + agregar una segunda capa de voz retrasada/pitcheada distinto, mezclada baja, para imitar el layering real que usó Sony.

---

## 1. Qué es "la voz de Venom" en realidad (no solo el DSP)

Busqué cómo se hizo en producción, no solo qué plugin de pitch-shift usar:

- El efecto es **layering**, no un solo filtro: Tom Hardy grababa su diálogo, el equipo de sonido lo mezclaba con grabaciones separadas de gruñidos/jadeos/sonidos guturales del propio Hardy, y en la primera película además se mezcló con la voz de un actor de voz separado (Brad Venable) para dar el timbre "otro ser hablando encima". El resultado es "un blend entre Eddie Brock y Venom", no Eddie con un filtro.
- Para las sesiones de ADR armaron una **cadena de efectos en tiempo real** que Hardy podía escuchar mientras grababa, para ajustar la actuación al resultado — es decir, el pitch-shift SÍ se aplicaba en vivo en su pipeline, confirma que es técnicamente posible hacerlo en tiempo real con las herramientas de post de cine (mucho más potentes que lo que corre en esta laptop, pero confirma que la idea "en vivo" no es descabellada).

Traducido a lo que ya existe en este proyecto: `audio_fx.FiltroUltratumba` (lowpass + ring-mod + saturación asimétrica + eco) ya cubre la parte "textura gutural/sucia" de la cadena. Lo que falta es (a) que el tono de base sea realmente más grave, no solo distorsionado, y (b) una segunda voz superpuesta, que es literalmente lo que hizo Sony.

## 2. Por qué el docstring actual descarta pitch-shift (y dónde se equivoca)

`audio_fx.py:1-11` dice que cualquier técnica que preserve duración "necesita ventanas de contexto que no calzan con un stream chunk-a-chunk sin introducir latencia creciente o cortes". Fui a confirmarlo con la librería más obvia primero.

### 2.1 `pedalboard.PitchShift` (Spotify, envuelve Rubber Band) — **descartada**

Instalé `pedalboard`, alimenté chunks de 200ms (mismo tamaño que manda la Live API a 24kHz) con `reset=False` (el modo streaming documentado):

```
chunk  0: in=4800 out=0     desfase_acumulado=+4800 samples
chunk  1: in=4800 out=0     desfase_acumulado=+9600 samples
chunk  2: in=4800 out=0     desfase_acumulado=+14400 samples
chunk  3: in=4800 out=0     desfase_acumulado=+19200 samples
chunk  4: in=4800 out=0     desfase_acumulado=+24000 samples
...
TOTAL tras 5s: desfase=25369 samples (1057ms de audio atrasado)
```

Los primeros ~5 chunks (1 segundo) devuelven **cero** samples de salida — el plugin bufferea internamente antes de emitir nada. CPU es barata (~1.5%), pero la latencia es inaceptable: enchufado a `_reproducir_loop`, Jarvis se quedaría mudo el primer segundo de cada respuesta y después hablaría con casi 1 segundo de atraso acumulado. Exactamente el síntoma que el docstring quería evitar — confirmado, pero por esta librería específica, no por "pitch-shift real" en general.

Causa raíz: `pedalboard.PitchShift` no expone el modo *RealTime* de Rubber Band ni el engine rápido — usa el motor de máxima calidad pensado para procesar archivos completos offline, que hace padding/lookahead grande a propósito.

### 2.2 `pylibrb` (bindings directos a Rubber Band) — **viable**

`pylibrb` expone la librería C++ completa, incluyendo las opciones que `pedalboard` esconde: `Option.PROCESS_REALTIME`, `Option.ENGINE_FASTER` (el motor "R2", ~3x más rápido que el de calidad máxima), `Option.WINDOW_SHORT`, `Option.FORMANT_PRESERVED`. Mismo test, mismos chunks de 200ms:

```
start_delay reportado por la librería: 384 samples (16.0ms)
chunk  0: in=4800 out=3821  desfase=+979 samples (+40.8ms)
chunk  1: in=4800 out=4745  desfase=+1034 samples (+43.1ms)
chunk  2: in=4800 out=4859  desfase=+975 samples (+40.6ms)
...
chunk 24: in=4800 out=4747  desfase=+1032 samples (+43.0ms)

TOTAL tras 5s: desfase=1032 samples (43.0ms) — CPU 1.2% del tiempo real, pico 3.25ms
```

Repetí con 150 chunks (30s simulados) para descartar que el desfase creciera lento en vez de estabilizarse:

```
desfase medio (chunks 50-150): 984 samples (41.0ms)
desfase min/max en todo el run: 884/1044 samples (36.8ms / 43.5ms)
desfase[10]=955 vs desfase[149]=1002 -> ESTABLE
```

**El desfase es un delay de pipeline fijo (~40ms), no un backlog que crece.** 40ms es imperceptible en una conversación — mucho menor que la ventana de eco (`_VENTANA_MUTEO_S = 0.6s`) que ya tolera el sistema. También corrí la cadena completa (`pylibrb` → `FiltroUltratumba.procesar()` existente, en `int16`) sobre las mismas 150 iteraciones sin excepciones.

Instalación: `pip install pylibrb` bajó un wheel precompilado para Windows (`amd64`), sin pedir Visual C++ Build Tools ni compilar nada — mismo nivel de fricción que instalar `numpy`.

### 2.3 Otras opciones consideradas y descartadas sin medir (o medidas parcial)

- **`pyrubberband`**: wrapper que escribe a archivos temporales y llama al CLI de Rubber Band por subprocess — no sirve para streaming en vivo, cada llamada es un proceso nuevo sobre un archivo completo. Descartada por diseño, no hizo falta medir.
- **`stftpitchshift`**: instalé, tardó varios minutos en compilar desde código fuente (no tiene wheel para Windows) — instalación mucho más frágil que `pylibrb`. Ventana STFT configurable (default 1024 muestras ≈ 43ms a 24kHz) sugiere latencia similar a `pylibrb`, pero no llegué a medirlo en profundidad porque `pylibrb` ya dio un resultado sólido y con mejor experiencia de instalación (wheel binario).
- **`pysoundtouch`** (dos forks distintos en GitHub): expone `put_samples()`/`get_samples()`, patrón streaming real igual que `pylibrb` — pero ambos forks requieren compilación manual contra la librería SoundTouch en C++, sin wheels. Descartada por fricción de instalación frente a una alternativa (`pylibrb`) que ya funciona.
- **WSOLA casero en numpy**: técnicamente viable (mismo patrón de estado-entre-chunks que ya usa `FiltroUltratumba`), la literatura reporta ~100ms de latencia típica para SOLA — peor que los 40ms medidos de `pylibrb`, y de escribir/ajustar el algoritmo a mano (evitar clicks en los empalmes de solapamiento) es trabajo de varios días. No vale la pena si `pylibrb` ya da mejor resultado gratis.

## 3. Propuesta de diseño (para cuando se implemente)

No implementado todavía — esto es lo que probaría primero, en orden:

1. **Pitch-down real** con `pylibrb`, `PROCESS_REALTIME | ENGINE_FASTER | FORMANT_PRESERVED`, arrancar en **-5 a -7 semitonos** (Venom real no es un pitch-down extremo tipo demonio de dibujo animado, es más sutil + la textura hace el resto). `initial_pitch_scale` se fija una vez al conectar la sesión, mismo patrón que `mic_device_index`.
2. **Encima**, el `FiltroUltratumba` actual (ya probado, ya barato) para el growl/textura — el orden importa: pitch-shift primero (trabaja mejor sobre la señal limpia), filtro cavernoso después.
3. **Capa secundaria** (lo que de verdad hace que suene "a dos voces", como el layering real de Sony): una segunda instancia de `pylibrb` con pitch distinto (ej. -12 semitonos) sobre el mismo audio, mezclada bajo (~20-30%) y con un pequeño delay (~15-20ms) respecto a la voz principal — imita la sensación de "otra cosa hablando encima" sin sacrificar inteligibilidad, porque la voz principal (bien pitcheada, formant-preserved) sigue siendo la que más se entiende.
4. Dejar el pitch/mezcla como valores en `config.py` (mismo patrón que `voz_ultratumba` ya usa) para poder ajustarlos a oído sin tocar código, igual que hicimos con `umbral_rms_eco`.

Lo que NO sabemos todavía porque hace falta oído humano real, no medición:
- Si -7 semitonos con formant preservado sigue sonando bien en la voz elegida (`Orus`/`Puck`/etc. de la Live API) — el material de prueba de hoy fue ruido sintético, no habla real.
- Si la capa secundaria con delay se siente "a dos voces" o solo "con eco raro" — esto es puramente de oído, no hay métrica objetiva.
- Costo de CPU total de la cadena completa (pitch principal + pitch secundario + `FiltroUltratumba` x2) en tiempo real sostenido, aunque cada pieza midió barata por separado.

## 4. Fuentes

- [pylibrb — GitHub](https://github.com/pawel-glomski/pylibrb) — bindings Python al RubberBandStretcher completo (offline y realtime)
- [Rubber Band Library — RubberBandStretcher class reference](https://breakfastquay.com/rubberband/code-doc/classRubberBand_1_1RubberBandStretcher.html) — documentación de modos Offline vs RealTime y engines R2/R3
- [pedalboard — Spotify, GitHub](https://github.com/spotify/pedalboard) — confirma que envuelve Rubber Band y soporta Windows amd64, pero no expone selección de engine/modo realtime
- [Behind The Voice: Decoding Venom's Iconic Growl](https://dl.iir.edu.ua/iir-news/behind-the-voice-decoding-venoms-iconic-growl-1764796796)
- [Sony Pictures Post Production Services Provides Stellar Sound for Columbia Pictures' Venom — HPA](https://hpaonline.com/sony-pictures-post-production-services-provides-stellar-sound-for-columbia-pictures-venom/) — confirma layering + cadena de efectos usada en vivo durante ADR
- [Why Tom Hardy's Venom Voice Is Different In Let There Be Carnage — ScreenRant](https://screenrant.com/venom-2-tom-hardy-voice-different-change-reason/)
- [WSOLA / time-pitch scaling overview — surina.net](https://www.surina.net/article/time-and-pitch-scaling.html) — referencia de ~100ms típico para SOLA, usado para comparar contra los 40ms medidos de `pylibrb`
