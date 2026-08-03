# JARVIS — Asistente de escritorio con voz

Asistente personal local para Windows: recordatorios, tareas, apertura de
apps, música de YouTube y charla por texto o por voz en tiempo real (Gemini
Live API), con una personalidad propia — sarcástico, metiche y con chistes
malos — definida en un solo lugar (`app/persona.py`).

> Este directorio (`Jarvis/`) es el proyecto real. El resto del repo
> (`Jarvis-Desktop-Voice-Assistant/`) es el clon original del que se partió
> y material de referencia — no se ejecuta.

## Cómo correr

```bash
pip install -r ../requirements.txt
python -m app.ui
```

Requisitos: Python 3.12 (usa `audioop`, removido en 3.13), Windows (overlay
usa la API Win32), API key de Gemini (se pega en el panel CONFIG de la app).

Al arrancar se abren:
1. **Ventana principal** (pywebview, 1000x700) — chat, tareas,
   recordatorios, configuración, tema espacial "Orbital Command".
2. **Overlay flotante** (proceso aparte) — nube de puntos animada en la
   esquina de la pantalla que refleja el estado de Jarvis. Se arrastra con
   el mouse, deja pasar los clics cuando no la tocás.

Atajo global **Ctrl+Espacio**: iniciar/detener la sesión de voz desde
cualquier ventana.

## Arquitectura

```
ui.py ──── lanza ──► overlay.py        (proceso aparte, Tk + Win32)
  │                      │ polling HTTP
  ├── thread ──► server.py (Flask, solo 127.0.0.1:5577)
  │                      │ delega en:
  └── pywebview          ├── actions/   tareas · recordatorios · open_app
      (assets/)          │              · musica · navegador
                         ├── gemini_agent.py   chat de texto
                         ├── voice_engine.py   voz en vivo (Live API)
                         └── config.py         datos/settings.json
```

- **Todo pasa por el Flask local** (`server.py`): la ventana principal y el
  overlay son clientes tontos que hacen polling de `/api/estado` y demás.
  Si el overlay crashea, Jarvis sigue; si la app muere, el overlay se
  cierra solo (30s sin servidor) y un mutex de Windows garantiza que nunca
  haya dos overlays vivos.
- **Tk y pywebview no conviven en un proceso** (ambos exigen el hilo
  principal) — por eso el overlay es un subprocess.

## Módulos (`app/`)

| Módulo | Qué hace |
|---|---|
| `ui.py` | Punto de entrada: Flask en thread + ventana pywebview + overlay |
| `server.py` | API HTTP local: tareas, recordatorios, chat, voz, config, mic-test |
| `persona.py` | **La personalidad**, compartida por texto y voz. Filo, chistes malos, pizca de superioridad, cuarta pared anclada al contexto. Un solo lugar para editarla |
| `gemini_agent.py` | Chat de texto: `matcher.py` local primero (gratis), Gemini con function-calling si no matchea, `buscar_web` con grounding |
| `matcher.py` | Regex/keywords para acciones deterministas sin gastar cuota |
| `voice_engine.py` | Sesión de voz Gemini Live: mic → servidor → audio. Reconexión con resumption handle, watchdog, transcripciones |
| `actions/` | Tools reales: `tareas`, `recordatorios` (+ runner de avisos), `open_app`, `musica` (YouTube por scraping), `navegador` |
| `overlay.py` | Esfera flotante: click-through dinámico, arrastre por polling del mouse, instancia única, autocierre sin servidor |
| `plexus.py` + `figuras.py` | Render de la nube de puntos por matemática en vivo — una figura por estado, morph al cambiar |
| `audio_fx.py` | Efecto "voz Venom" opcional (pitch/capas) sobre el audio de salida |
| `tts_local.py` | Voz local pyttsx3 para avisos de recordatorios (sin gastar Gemini) |
| `config.py` | Lee/escribe `datos/settings.json` |
| `_check_*.py` | Self-checks manuales que requieren hardware/red |

Interfaz en `assets/` (HTML/CSS/JS servidos por Flask): tema espacial
portado de `../stitch_jarvis_cosmic_terminal/orbital_command/DESIGN.md`
(Space Mono, bordes 1px, cero border-radius, acento rojo `#e0102a`), con
nebulosa + estrellas en canvas 2D que reaccionan al estado real
(inactivo/escuchando/procesando/hablando). En reposo el bucle de animación
se corta — cero CPU.

## Voz: decisiones que no hay que deshacer

Documentadas con causa raíz en `../plans/ERRORES.md` — las tres costaron
días:

1. **Con parlantes, el mic va en MUTE total mientras Jarvis suena** (se
   manda silencio, no se corta el stream). Se intentó dos veces distinguir
   eco de voz por energía (RMS) y ambas fallaron: Jarvis se transcribía a
   sí mismo como usuario y se auto-interrumpía en bucle. Interrumpir con
   parlantes = Ctrl+Espacio. Con auriculares el barge-in por voz funciona
   completo. El upgrade real es AEC (webrtc-apm/speexdsp).
2. **Nunca cortar el envío de audio del todo** — rompe el VAD del servidor
   para el resto de la sesión. Silencio del mismo tamaño, siempre.
3. **`session.receive()` es un generador POR TURNO** — va dentro de un
   `while`, o la sesión queda viva pero sorda tras la primera respuesta.

Modelo: `gemini-3.1-flash-live-preview` (el native-audio ignora los schemas
de las tools — verificado contra la API real).

## Datos

`datos/` (JSON plano, editable a mano): `settings.json` (API key, voz,
dispositivos, flags), `tareas.json`, `recordatorios.json`, `alarmas.json`.

## Documentación relacionada

- `../plans/README.md` — plan por fases (18/20 completas; pendientes: 07
  clima/morning-brief, 10 reemplazada por el overlay actual)
- `../plans/ERRORES.md` — bitácora de errores reales con causa raíz y
  reglas aprendidas. **Leerla antes de tocar voz o overlay.**
- `../plans/INVESTIGACION-*.md` — investigaciones técnicas (Live API,
  overlay Win32, sistema de partículas, voz Venom)
- `app/persona.py` — el docstring explica la calibración del filo y por
  qué los EJEMPLOS son la parte que más pesa del prompt

## Estado actual / pendientes

- Voz, tareas, recordatorios, apps, música, chat y overlay: funcionando.
- Pendiente: fase 07 (clima + morning brief), AEC real para barge-in con
  parlantes, empaquetado a `.exe` (PyInstaller) para distribuir.
- `audioop` está deprecado (removal en Python 3.13) — atado a Python 3.12
  hasta reemplazarlo.
