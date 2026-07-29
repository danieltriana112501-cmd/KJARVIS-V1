"""audio_fx.py — Filtro cavernoso opcional sobre el audio de salida de voz.

Pitch-shift real (bajar el tono) no es seguro acá: la Live API entrega el
audio en chunks chicos en tiempo real, y cualquier técnica de pitch-shift
que preserve la duración (phase vocoder, PSOLA) necesita ventanas de
contexto que no calzan con un stream chunk-a-chunk sin introducir latencia
creciente o cortes — justo el tipo de problema de audio que ya costó horas
de debugging en este proyecto (ver plans/ERRORES.md). Un pitch-shift
"barato" por resampleo cambiaría la duración del audio, y la cola de
reproducción (`voice_engine._reproducir_loop`) se iría desincronizando del
tiempo real.

Lo que sí es seguro en un stream chunk-a-chunk, porque ninguno necesita
ventana de contexto más allá de una muestra (o un contador de fase
continuo, que es igual de barato):

- pasabajos de un polo — apaga agudos, da tono apagado/cavernoso.
- modulación en anillo (portadora ~40Hz) — mete el timbre metálico/
  "poseído", típico de voz distorsionada de ultratumba.
- saturación (soft clip con `tanh`) — distorsión armónica real, no solo
  eco. Es no lineal pero por-muestra, sin memoria, así que tampoco corre
  riesgo de desincronizar el stream.
- eco corto con feedback — resonancia de cueva.

Todos con estado de UNA muestra (o una fase) de memoria, así que el estado
viaja de un chunk al siguiente sin clicks.
"""
from __future__ import annotations

import numpy as np


class FiltroUltratumba:
    def __init__(self, sample_rate: int):
        self._sr = sample_rate

        self._alfa_lp = 0.35
        self._prev_lp = 0.0

        self._freq_mod = 45.0
        self._mezcla_mod = 0.5
        self._muestra_idx = 0

        self._drive = 2.2

        self._feedback = 0.35
        self._mezcla_eco = 0.35
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

        drive = self._drive
        techo = np.tanh(drive)
        saturadas = np.tanh(moduladas / 32768.0 * drive) * (32768.0 / techo)

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
