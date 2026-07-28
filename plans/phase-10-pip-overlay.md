# Fase 10 — Ventana flotante mini (picture-in-picture)

## Objetivo

Agregar una segunda ventana pequeña, sin bordes, siempre encima de las
demás, ubicada en una esquina del escritorio, mostrando la misma animación
ASCII del panel central (Fase 09) en tamaño reducido — para dar la
sensación de que "Jarvis está activo y escuchando" incluso con la ventana
principal minimizada o en otra pantalla.

## Contexto

Depende de la **Fase 09** (reutiliza la misma animación/lógica, no debe
duplicarse) y de la **Fase 08** (la app ya debe tener el shell
pywebview + Flask corriendo).

## Alcance de esta fase

### 1. Página mini reutilizando el mismo HTML/JS

No crear una página HTML separada con lógica duplicada. En cambio:

- Agregar un parámetro de query string a la página existente, ej.
  `http://127.0.0.1:<puerto>/?modo=mini`.
- En `Jarvis/assets/app.js`, al detectar `modo=mini` en la URL, ocultar
  todo excepto el contenedor de la animación ASCII (sidebar, header,
  modales, caption largo — todo `display:none` vía una clase `body.mini`
  agregada por JS) y reducir el tamaño de la grilla de caracteres para que
  entre cómodo en una ventana chica (ej. 320x320 px).
- Mantener el polling a `/api/estado` igual que en la ventana principal —
  ambas ventanas reflejan el mismo estado real, no hace falta sincronizar
  nada especial entre ellas (las dos leen del mismo backend).

### 2. Segunda ventana pywebview

En `Jarvis/app/ui.py` (Fase 08), agregar la creación de una segunda
ventana con `webview.create_window(...)`:

```python
webview.create_window(
    "Jarvis Mini",
    url=f"http://127.0.0.1:{puerto}/?modo=mini",
    width=200, height=200,
    x=<calcular esquina inferior derecha de la pantalla>,
    y=<calcular esquina inferior derecha de la pantalla>,
    frameless=True,
    easy_drag=True,      # permite arrastrarla para reposicionar sin bordes
    on_top=True,
    transparent=True,
    resizable=False,
)
```

Calcular `x`/`y` para esquina inferior derecha: usar
`webview.screens[0].width/height` (o el método equivalente que exponga la
versión de `pywebview` instalada — confirmar el API exacto contra la
versión real del paquete al implementar, puede variar) menos el tamaño de
la ventana mini y un margen (ej. 24px).

### 3. Toggle de mostrar/ocultar

Agregar un botón en la ventana principal (header, junto al botón de
voz de la Fase 08) para mostrar/ocultar la ventana mini bajo demanda —
no forzar que esté siempre abierta si el usuario no la quiere. Usar
`window.hide()` / `window.show()` de `pywebview` sobre la referencia de
la ventana mini guardada al crearla.

### 4. Persistir la preferencia

Guardar en `Jarvis/app/config.py` (Fase 01) un campo nuevo
`"pip_habilitado": false` en `DEFAULTS`, para que la próxima vez que se
abra la app recuerde si el usuario quiere la ventana mini activa por
defecto o no.

## Fuera de alcance

- No implementar click-through (que los clicks atraviesen la ventana
  hacia lo que esté debajo) — con poder arrastrarla y ocultarla a demanda
  alcanza para esta fase; click-through depende de APIs nativas de Windows
  no garantizadas por `pywebview` en todas sus versiones, evaluarlo aparte
  si en el futuro molesta.
- No agregar más contenido a la ventana mini que la animación + el texto
  de estado corto — nada de caption largo, nada de controles.

## Verificación

Manual:

1. Activar el toggle de ventana mini, confirmar que aparece una ventana
   sin bordes en la esquina inferior derecha del escritorio, encima de
   cualquier otra ventana (probar con el navegador o el explorador de
   archivos abierto en pantalla completa detrás).
2. Confirmar que la animación ASCII se ve reducida pero legible.
3. Hablarle al asistente (Fase 06) con la ventana principal minimizada,
   confirmar que la ventana mini refleja el cambio de estado
   (inactivo → escuchando → hablando) en tiempo real.
4. Ocultar la ventana mini con el toggle, confirmar que desaparece sin
   cerrar la app principal.
5. Cerrar y reabrir la app, confirmar que la preferencia de
   `pip_habilitado` se respetó.

## Entregable final de la fase

- Segunda ventana `pywebview` funcionando: sin bordes, siempre encima,
  arrastrable, en esquina configurable.
- Modo `?modo=mini` en el frontend reutilizando la misma animación de la
  Fase 09 sin duplicar código.
- Toggle de mostrar/ocultar + preferencia persistida.
- Marcar `- [x] Fase 10` en `plans/README.md`.

## Cierre del plan

Esta es la última fase del plan original. Al completarla, el asistente
cubre todo el alcance acordado: tareas, recordatorios/alarmas con acción
real al sonar, apertura de apps, música vía YouTube, búsqueda con
grounding, agente Gemini con ahorro de cuota vía matcher local, voz nativa
Gemini Live bajo demanda, clima + morning brief, interfaz Watch Dogs 2
monocromática con panel ASCII animado y ventana flotante mini. Cualquier
funcionalidad adicional a partir de acá (wake-word, click-through, más
integraciones) queda fuera de este plan y debería definirse como un plan
nuevo, no como un agregado silencioso a estas fases ya cerradas.
