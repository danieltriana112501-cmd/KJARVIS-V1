# Fase 15 — VAD: agregar `silence_duration_ms`, segunda variable aislada

## Objetivo

El usuario confirmó en vivo, con auriculares puestos y `prefix_padding_ms`
ya andando bien (Fase 14): **el servidor no lo deja terminar de hablar** —
corta su turno antes de que termine, y Jarvis responde de todos modos.
Confirmado por el log real de esa sesión: los `interrupted` no eran ruido
de fondo ni autointerrupciones de tools — el usuario mismo lo sintió al
hablar.

Esto es exactamente lo que `silence_duration_ms` controla: cuánto silencio
tiene que pasar antes de que el servidor decida "terminó de hablar". Sin
configurarlo explícito, se usa el default del servidor (~800ms según la
doc, pero el síntoma reportado sugiere que en la práctica corta antes).

Referencia: `plans/INVESTIGACION-2026-07-27-voz-tools-ui.md`, sección 2.4.

## Contexto

Sigue la regla de una variable por vez. La Fase 14 ya agregó
`prefix_padding_ms=300` en aislado y confirmó que el servidor no se queda
mudo (a diferencia del desastre de Fase 06). Esta fase agrega la SEGUNDA
variable, `silence_duration_ms`, también aislada — sin tocar sensibilidades
todavía.

## Alcance de esta fase

En `Jarvis/app/voice_engine.py`, dentro de `AutomaticActivityDetection` (ya
existente desde la Fase 14), agregar:

```python
silence_duration_ms=800,
```

800ms es el techo del rango que la documentación oficial recomienda
(500-800ms; por debajo de 500 fragmenta el habla en pausas naturales). Se
elige el techo, no un valor intermedio, porque el síntoma reportado es
"corta corto" — dar más margen es la dirección correcta del ajuste.

## Fuera de alcance

- **Sensibilidades** (`start_of_speech_sensitivity` /
  `end_of_speech_sensitivity`) — siguen para una fase futura, solo si
  `silence_duration_ms=800` no alcanza.
- **VAD manual** (`disabled: true` + `activity_start`/`activity_end`) —
  cambio de arquitectura mayor, no esta fase.
- Nada del resto del plan (tools, prompt, personaje).

## Verificación

Automatizable:

1. `python -c "from google.genai import types; types.RealtimeInputConfig(automatic_activity_detection=types.AutomaticActivityDetection(prefix_padding_ms=300, silence_duration_ms=800))"` sin error.
2. Import + self-check de `voice_engine.py` sin romperse.

**Manual, obligatoria:**

3. Sesión de voz real, auriculares puestos. Hablar con pausas naturales
   (frases largas, dudar a mitad de la oración) y confirmar que el
   servidor espera a que el usuario termine antes de responder.
4. Confirmar que el servidor sigue mandando mensajes con normalidad (no se
   quedó mudo).
5. Si 800ms sigue cortando corto, o si ahora tarda demasiado en responder,
   reportarlo — es información válida, no forzar una conclusión positiva.

## Entregable final de la fase

- `silence_duration_ms=800` agregado, aislado, junto a `prefix_padding_ms`.
- Resultado real de la prueba manual documentado.
- Marcar `- [x] Fase 15` en `plans/README.md` **solo si el usuario confirma
  en vivo que mejoró (o al menos no empeoró) y el servidor sigue
  funcionando**.
