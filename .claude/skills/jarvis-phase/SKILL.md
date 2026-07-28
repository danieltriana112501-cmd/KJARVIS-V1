---
name: jarvis-phase
description: Ejecuta UNA fase del plan de reconstrucción de Jarvis (plans/phase-NN-*.md) de punta a punta — construir, revisar, y marcar como completa. Usar cuando el usuario diga "ejecuta la fase N", "avanza con la fase N del plan de Jarvis", "implementa la siguiente fase" o similar. Argumento: número de fase (01-10).
---

# Ejecutar una fase del plan de Jarvis

Esta skill orquesta el ciclo completo de una fase del plan en
`plans/phase-NN-*.md`: construir → revisar → marcar como completa. No la
uses para trabajo fuera de ese plan (ese plan es específico del proyecto
`Jarvis-Desktop-Voice-Assistant`, uso personal, no comercial).

## Pasos

1. **Determinar la fase**: si el usuario dio un número, usar ese. Si no
   dio ninguno, leer `plans/README.md` y tomar la primera fase sin marcar
   `[x]` en la tabla de estado — pero SIEMPRE confirmar con el usuario
   cuál fase se va a ejecutar antes de arrancar (puede que quiera saltear
   una o repetir una ya hecha).

2. **Chequeo de dependencias**: leer la fila de la fase en la tabla del
   índice de `plans/README.md` (columna "Depende de"). Si alguna fase
   dependiente no está marcada `[x]`, avisar al usuario y preguntar si
   igual quiere continuar (puede que la haya hecho manualmente sin
   marcarla) o si primero hay que hacer la dependencia.

3. **Construir**: delegar la implementación con el tool `Agent`,
   `run_in_background: false` (necesitás el resultado antes de revisar):
   - Fases 01–07 → `subagent_type: jarvis-builder`.
   - Fases 08–10 → `subagent_type: jarvis-ui-builder`.
   El prompt al agente debe decir explícitamente qué archivo de fase
   implementar (ej. "Implementá `plans/phase-03-recordatorios.md`
   completo.") — no resumas el contenido del plan en el prompt, el agente
   lo lee solo, así no se pierde nada por una mala paráfrasis tuya.

4. **Revisar**: con el resultado del builder, delegar a `Agent` con
   `subagent_type: jarvis-reviewer`, `run_in_background: false`, pidiendo
   explícitamente que revise esa misma fase.

5. **Según el veredicto del reviewer**:
   - **APROBADA**: editar `plans/README.md` marcando `- [x] Fase NN` en
     la sección de Estado. Informar al usuario: qué se hizo, qué quedó
     pendiente de confirmación humana (si algo requería probar de viva
     voz o ver la ventana), y cuál es la siguiente fase disponible según
     el índice.
   - **RECHAZADA**: NO marcar la casilla. Mostrar al usuario la lista de
     problemas que reportó el reviewer, priorizados. Preguntar si querés
     mandar a corregir con otro pase del builder (mismo agente, mismo
     `subagent_type`, con el prompt de corrección incluyendo los FAILs
     puntuales) o si el usuario prefiere revisarlo él mismo primero.

6. **Nunca** encadenar automáticamente a la fase siguiente sin que el
   usuario lo pida — el plan es explícitamente de fases cortas para que
   el usuario decida, fase por fase, si seguir según su cuota diaria
   disponible.

## Notas

- Esta skill no reemplaza la lectura de `plans/README.md` — si es la
  primera vez que se usa en la sesión, leerlo completo primero para tener
  el contexto de principios globales (ahorro de cuota, seguridad,
  estética) antes de delegar nada.
- `plans/ERRORES.md` es la bitácora de errores/aprendizajes del proyecto.
  Los subagentes (`jarvis-builder`, `jarvis-ui-builder`, `jarvis-reviewer`)
  ya la leen y la actualizan por su cuenta cuando corresponde — no hace
  falta que la skill la administre directamente. Pero si el reviewer
  marca una "REGRESIÓN de error conocido" en su reporte, tratala como un
  FAIL automático (RECHAZADA) sin importar el resto del veredicto: repetir
  un error ya documentado es peor que uno nuevo.
- Si el usuario pide ejecutar una fase de interfaz (08-10) y las fases
  01-05 no están completas, la skill debe advertirlo con claridad — esas
  fases de UI necesitan un backend real para conectar, no tiene sentido
  construir la interfaz antes.
