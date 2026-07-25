"""FM-демодуляция квадратурным дискриминатором (angle-difference)."""

from __future__ import annotations

import numpy as np


class FmDemodulator:
    """Мгновенная частота = разность фаз соседних отсчётов уже перенесённого
    на 0 Гц канала: angle(x[n] * conj(x[n-1])), с масштабированием так, что
    полная паспортная девиация канала (deviation_hz) даёт амплитуду ~1.0.

    В отличие от AM (stateless np.abs), здесь нужен последний отсчёт
    предыдущего чанка — иначе на границе между вызовами process() фаза
    разрывается и на стыке блоков возникает щелчок. Тот же приём, что уже
    используется в проекте для потокового состояния фильтров (zi у
    AudioFilter/Decimator/AudioResampler), только состояние — один комплексный
    отсчёт, а не вектор коэффициентов фильтра.
    """

    def __init__(self, sample_rate_hz: float, deviation_hz: float) -> None:
        self._scale = np.float32(sample_rate_hz / (2.0 * np.pi * deviation_hz))
        # Холодный старт: до начала записи сигнала не было (тот же смысл,
        # что у нулевого zi в AudioFilter) — даёт один "лишний" разностный
        # отсчёт в начале потока, но не искажает ничего дальше него.
        self._prev_sample = np.complex64(0.0)

    def process(self, channel_samples: np.ndarray) -> np.ndarray:
        if channel_samples.size == 0:
            return np.empty(0, dtype=np.float32)

        extended = np.concatenate(([self._prev_sample], channel_samples))
        self._prev_sample = channel_samples[-1]

        phase_diff = np.angle(extended[1:] * np.conj(extended[:-1]))
        return (phase_diff * self._scale).astype(np.float32)
