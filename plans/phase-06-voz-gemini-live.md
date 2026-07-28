# Fase 06 — Motor de voz nativo (Gemini Live API)

## Objetivo

Reemplazar el reconocimiento de voz y síntesis de voz local (usados hasta
ahora solo para probar las fases anteriores) por una sesión de voz nativa
usando la Live API de Gemini — el usuario pidió explícitamente hablar con
la voz de Gemini, no con TTS genérico.

## Contexto

Depende de la **Fase 05** (el agente de texto con function-calling ya
debe existir y funcionar — la Live API también soporta function-calling
directo, pero para no duplicar lógica, esta fase reutiliza
`GeminiAgent` como el "cerebro" y la Live API solo se encarga de la capa
de audio in/out).

Decisión ya tomada con el usuario, importante para no reabrir el tema:

- **Cuota de Live API es más limitada que la de texto** — la sesión de voz
  se abre **solo bajo demanda** (por ejemplo al detectar una palabra de
  activación, o al presionar un botón/tecla), nunca queda escuchando en
  streaming continuo todo el día.
- Una conexión Live dura un tiempo limitado (~15 minutos en audio solo,
  según la documentación vigente al momento del diseño — **confirmar el
  límite actual en la documentación oficial antes de asumir el número**,
  puede haber cambiado) antes de cortarse sola; hay que reconectar o usar
  "session resumption" si el SDK lo soporta en ese momento.
- El usuario eligió la voz en el módulo de configuración (Fase 01,
  `VOCES_DISPONIBLES`) — la sesión Live debe usar esa voz.

## Alcance de esta fase

### 1. Dependencias nuevas

`google-genai` ya está (Fase 05). Puede requerir además una librería de
audio para capturar mic y reproducir output PCM — evaluar al implementar
cuál da menos fricción en Windows (candidatas: `sounddevice` o `pyaudio`;
preferir `sounddevice` si no da problemas de instalación en Windows, es
más simple que `pyaudio`). Agregar la elegida a `requirements.txt`.

### 2. Clase desacoplada `VoiceEngine`

Crear `Jarvis/app/voice_engine.py`:

```python
class VoiceEngine:
    def __init__(self, api_key: str, voice: str, agente: GeminiAgent): ...

    def iniciar_sesion(self) -> None:
        """Abre una sesión Live, empieza a escuchar el micrófono."""

    def detener_sesion(self) -> None:
        """Cierra la sesión Live activa, si hay una."""

    @property
    def activo(self) -> bool: ...
```

Esta clase debe quedar **desacoplada** a propósito (esto ya se lo
confirmamos al usuario): el resto del sistema no debe asumir que la voz
viene de Gemini Live específicamente. Si en el futuro se cambia de
proveedor de voz (por agotar cuota, por ejemplo), solo se reemplaza esta
clase — ningún otro módulo (`tareas`, `recordatorios`, `gemini_agent`,
etc.) debe importar nada de `voice_engine.py` directamente ni saber que
existe Live API.

Function-calling dentro de la sesión Live: cuando el modelo, durante la
conversación de voz, decide llamar a una tool (tarea, recordatorio, abrir
app, música, buscar web), la sesión debe delegar la ejecución real a las
mismas funciones que ya usa `GeminiAgent` (no reimplementar el dispatch de
tools acá — importar y reutilizar).

### 3. Activación bajo demanda

Implementar un mecanismo simple de arranque/parada de sesión — la forma
más simple y ya usada en el proyecto original (`Jarvis/jarvis.py`) es un
botón "Start Listening" / tecla. Para esta fase (todavía sin interfaz
gráfica nueva, eso es Fase 08), alcanza con exponerlo como método directo
de `VoiceEngine` que se pueda llamar desde un script de prueba por
teclado (ej. Enter para empezar, Enter de nuevo para cortar). La Fase 08
lo conecta a un botón real.

### 4. Selector de voz desde config

`VoiceEngine` debe leer la voz activa desde `Jarvis/app/config.py`
(`get("voice")`) al iniciar sesión, no hardcodear ninguna voz.

## Fuera de alcance

- No implementar wake-word (detección de palabra de activación tipo "Hey
  Jarvis") en esta fase — eso puede ser una mejora futura fuera de este
  plan de fases; por ahora la activación es manual (botón/tecla).
- No tocar la interfaz gráfica (Fase 08/09 se conectan a esto después).
- No implementar reconexión automática robusta ante cortes de red — con
  un mensaje de error claro y la posibilidad de reintentar manualmente
  alcanza para esta fase.

## Verificación

Como esto requiere hablarle de verdad al sistema (no es automatizable sin
un humano), el self-check es un script manual
`Jarvis/app/_check_voz.py` con instrucciones impresas:

1. Corre `voice_engine.iniciar_sesion()`.
2. Imprime en consola: "Sesión iniciada. Decí algo como 'qué hora es' o
   'agrégame una tarea para mañana'."
3. El humano prueba de viva voz, confirma que:
   - Se escucha la respuesta con la voz elegida en config.
   - Una acción simple (tarea/recordatorio) efectivamente se guarda (se
     puede confirmar leyendo el JSON en `Jarvis/datos/`).
4. Corre `voice_engine.detener_sesion()`, confirma que el mic deja de
   escuchar.

Documentar en el propio script que este check consume cuota de Live API
real — no correrlo repetidamente sin necesidad.

## Entregable final de la fase

- `Jarvis/app/voice_engine.py` con sesión Live funcional, voz configurable,
  activación/desactivación manual, function-calling delegado a
  `GeminiAgent`.
- `requirements.txt` actualizado.
- Verificación manual documentada y realizada al menos una vez.
- Marcar `- [x] Fase 06` en `plans/README.md`.
