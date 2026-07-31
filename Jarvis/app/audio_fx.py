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
- modulación en anillo (portadora grave, ~30Hz) — mete el timbre metálico/
  gutural.
- saturación ASIMÉTRICA (`tanh` con drive distinto en el semiciclo positivo
  y negativo) — a diferencia de un clip simétrico, esto mete armónicos
  PARES, que es lo que da el "buzz"/gruñido (growl) de una voz tipo
  Venom/monstruo en vez de una distorsión pareja de guitarra. Sigue siendo
  no lineal pero por-muestra, sin memoria.
- eco corto con feedback — resonancia de cueva.

Todos con estado de UNA muestra (o una fase) de memoria, así que el estado
viaja de un chunk al siguiente sin clicks. Un pitch-down real (más grave de
verdad, no solo más distorsionado) sigue sin ser seguro acá por el motivo
de arriba — esto se acerca al carácter (gutural, sucio, cavernoso) sin
tocar la duración del audio.
"""
from __future__ import annotations

import numpy as np


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
