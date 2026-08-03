"""audio_fx.py — Cadena de efectos "voz de Venom" sobre el audio de salida.

Dos piezas, en orden:

1. `_PitchDownRealtime` — pitch-down REAL vía Rubber Band en modo
   `PROCESS_REALTIME` (`pylibrb`, bindings directos — no `pedalboard`, que
   solo expone el motor offline de Rubber Band). Medido en
   `plans/INVESTIGACION-2026-07-30-voz-venom.md`: `pedalboard.PitchShift`
   bufferea ~1s antes de devolver audio y el atraso crece sin techo
   (inutilizable acá); `pylibrb` en modo realtime da ~40ms de latencia FIJA
   (no crece), confirmado sobre 30s simulados. Con `FORMANT_PRESERVED` para
   que grave no suene "voz de persona chica en tono grave".
2. `FiltroUltratumba` — pasabajos + modulación en anillo + saturación
   asimétrica (armónicos pares = growl) + eco, todo con estado de UNA
   muestra de memoria (sin ventana de contexto, sin latencia extra). Igual
   que antes de esta investigación.

`FiltroVenom` compone ambas más una CAPA SECUNDARIA (segunda voz, pitch más
grave todavía, mezclada baja con un chunk de retraso) — la referencia real
de cómo Sony hizo la voz de Venom no es un filtro solo, es layering: la voz
de Tom Hardy mezclada con una segunda voz separada (ver la investigación).
Sin la capa secundaria, esto es solo "Jarvis con voz grave", no Venom.
"""
from __future__ import annotations

import numpy as np
import pylibrb as _rb


class FiltroUltratumba:
    def __init__(self, sample_rate: int):
        self._sr = sample_rate

        self._alfa_lp = 0.35
        self._prev_lp = 0.0

        self._freq_mod = 30.0
        self._mezcla_mod = 0.6
        self._muestra_idx = 0

        self._drive_pos = 5.5
        self._drive_neg = 2.5

        self._feedback = 0.4
        self._mezcla_eco = 0.4
        self._buffer = np.zeros(int(sample_rate * 0.05), dtype=np.float32)
        self._pos = 0

    def procesar(self, datos: bytes) -> bytes:
        muestras = np.frombuffer(datos, dtype=np.int16).astype(np.float32)
        if muestras.size == 0:
            return datos
        n = muestras.size

        filtradas = np.empty_like(muestras)
        prev = self._prev_lp
        alfa = self._alfa_lp
        for i in range(n):
            prev += alfa * (muestras[i] - prev)
            filtradas[i] = prev
        self._prev_lp = prev

        t = (self._muestra_idx + np.arange(n)) / self._sr
        portadora = 1.0 - self._mezcla_mod + self._mezcla_mod * np.abs(
            np.sin(2.0 * np.pi * self._freq_mod * t)
        )
        moduladas = filtradas * portadora
        self._muestra_idx += n

        techo_pos = np.tanh(self._drive_pos)
        techo_neg = np.tanh(self._drive_neg)
        positivas = np.clip(moduladas, 0, None)
        negativas = np.clip(moduladas, None, 0)
        saturadas = (
            np.tanh(positivas / 32768.0 * self._drive_pos) * (32768.0 / techo_pos)
            + np.tanh(negativas / 32768.0 * self._drive_neg) * (32768.0 / techo_neg)
        )

        buf, tam, pos = self._buffer, self._buffer.size, self._pos
        feedback, mezcla_eco = self._feedback, self._mezcla_eco
        salida = np.empty_like(saturadas)
        for i in range(n):
            eco = buf[pos]
            salida[i] = saturadas[i] + mezcla_eco * eco
            buf[pos] = saturadas[i] + feedback * eco
            pos = (pos + 1) % tam
        self._pos = pos

        np.clip(salida, -32768, 32767, out=salida)
        return salida.astype(np.int16).tobytes()


class _PitchDownRealtime:
    """Pitch-down real vía Rubber Band en modo tiempo real. Ver
    `plans/INVESTIGACION-2026-07-30-voz-venom.md`: `PROCESS_REALTIME` +
    `ENGINE_FASTER` da ~40ms de latencia FIJA (medido, no crece en 30s
    simulados) — el motor offline que usa `pedalboard` en cambio acumula
    ~1s de atraso sin techo, inutilizable en un stream en vivo."""

    def __init__(self, sample_rate: int, semitonos: float):
        opciones = (
            _rb.Option.PROCESS_REALTIME
            | _rb.Option.ENGINE_FASTER
            | _rb.Option.FORMANT_PRESERVED
            | _rb.Option.WINDOW_SHORT
        )
        escala = 2.0 ** (semitonos / 12.0)
        self._stretcher = _rb.RubberBandStretcher(
            sample_rate, 1, opciones, initial_pitch_scale=escala,
        )

    def procesar_float(self, muestras_int16: np.ndarray) -> np.ndarray:
        """`muestras_int16` es 1D int16 ya decodificado. Devuelve float32 1D
        en [-1, 1] — el largo NO tiene por qué coincidir con el de entrada
        (Rubber Band bufferea internamente, ver la latencia de arriba)."""
        audio = (muestras_int16.astype(np.float32) / 32768.0).reshape(1, -1)
        self._stretcher.process(audio, final=False)
        salida = self._stretcher.retrieve_available()
        return salida[0] if salida.size else np.empty(0, dtype=np.float32)


class FiltroVenom:
    """Cadena completa: pitch-down real (voz principal) + una segunda voz
    más grave todavía mezclada baja con un chunk de retraso (imita el
    layering real que usó Sony — ver la investigación, no es solo un
    filtro) + `FiltroUltratumba` (growl/textura) encima de la mezcla."""

    _SEMITONOS_PRINCIPAL = -6.0
    _SEMITONOS_SECUNDARIA = -12.0
    _MEZCLA_SECUNDARIA = 0.25

    def __init__(self, sample_rate: int):
        self._principal = _PitchDownRealtime(sample_rate, self._SEMITONOS_PRINCIPAL)
        self._secundaria = _PitchDownRealtime(sample_rate, self._SEMITONOS_SECUNDARIA)
        self._ultratumba = FiltroUltratumba(sample_rate)
        # ponytail: retraso de la capa secundaria = "lo que sobró del chunk
        # anterior" (no un ring buffer con retraso exacto en ms) — alcanza
        # para el efecto "segunda voz encima" a oído. Si no se siente
        # separada de la principal, subir a un buffer circular con retraso
        # configurable en milisegundos.
        self._secundaria_previa = np.empty(0, dtype=np.float32)

    def procesar(self, datos: bytes) -> bytes:
        muestras = np.frombuffer(datos, dtype=np.int16)
        if muestras.size == 0:
            return datos

        principal = self._principal.procesar_float(muestras)
        secundaria = self._secundaria.procesar_float(muestras)

        if principal.size and self._secundaria_previa.size:
            n = min(principal.size, self._secundaria_previa.size)
            principal[:n] += self._secundaria_previa[:n] * self._MEZCLA_SECUNDARIA
        self._secundaria_previa = secundaria

        if principal.size == 0:
            # Los primeros chunks pueden no devolver nada todavía mientras
            # Rubber Band llena su buffer interno (~40ms) — no es un error,
            # el audio llega en el chunk siguiente.
            return b""

        pcm16 = np.clip(principal * 32768.0, -32768, 32767).astype(np.int16)
        return self._ultratumba.procesar(pcm16.tobytes())


def _check() -> None:
    """Self-check sin audio real: genera un tono puro de 200Hz, lo pasa por
    `FiltroVenom` y confirma con FFT que la frecuencia dominante de salida
    bajó de verdad (no solo que el filtro no explota) — la parte que un
    self-check sin oído SÍ puede verificar objetivamente."""
    sr = 24000
    f0 = 200.0
    chunk_ms = 200
    chunk_n = int(sr * chunk_ms / 1000)
    n_chunks = 20  # 4s — suficiente para que el pitch-shifter se estabilice

    venom = FiltroVenom(sr)
    idx_global = 0
    ultimos_chunks = []
    for i in range(n_chunks):
        t = (idx_global + np.arange(chunk_n)) / sr
        tono = (np.sin(2.0 * np.pi * f0 * t) * 20000).astype(np.int16)
        idx_global += chunk_n
        salida = venom.procesar(tono.tobytes())
        if i >= n_chunks - 5:  # solo los últimos chunks, ya estabilizado
            ultimos_chunks.append(np.frombuffer(salida, dtype=np.int16))

    salida_estable = np.concatenate([c for c in ultimos_chunks if c.size])
    assert salida_estable.size > sr // 4, "muy poca salida estable para analizar"

    espectro = np.abs(np.fft.rfft(salida_estable.astype(np.float64)))
    freqs = np.fft.rfftfreq(salida_estable.size, d=1.0 / sr)
    f_dominante = freqs[np.argmax(espectro)]

    f_esperada = f0 * (2.0 ** (FiltroVenom._SEMITONOS_PRINCIPAL / 12.0))
    assert abs(f_dominante - f_esperada) < 15.0, (
        f"pitch-down no bajo como se esperaba: entrada={f0}Hz, "
        f"esperado~{f_esperada:.1f}Hz, medido={f_dominante:.1f}Hz"
    )
    assert f_dominante < f0 * 0.9, "la frecuencia de salida deberia ser claramente mas grave"

    print(f"OK (tono {f0:.0f}Hz -> {f_dominante:.1f}Hz, esperado~{f_esperada:.1f}Hz)")


if __name__ == "__main__":
    _check()
