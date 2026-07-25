"""Потоковый ФНЧ + целочисленная децимация — общий примитив для канального
конвейера (ChannelExtractor) и финального ресемплинга аудио (AudioResampler).

Работает как с комплексными (IQ), так и с вещественными (аудио) отсчётами.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import firwin


class Decimator:
    """ФНЧ (FIR) с потоковым состоянием + децимация в `factor` раз.

    Фильтрует и прореживает произвольные по длине чанки, сохраняя фазу
    децимации и состояние фильтра между вызовами process() — так на стыках
    чанков не возникает щелчков/разрывов, независимо от того, кратна ли
    длина чанка factor.

    Реализация — не "отфильтровать всё через lfilter, потом прорядить"
    (там 96% посчитанного при factor=25 тут же выбрасывается), а прямое
    вычисление только нужных выходных отсчётов через скользящие окна:

    lfilter(taps, [1], x, zi=...)[m] математически равен
    dot(taps[::-1], extended[m : m+ntaps]), где extended = history ++ x,
    history — последние (ntaps-1) реальных отсчётов (изначально нули — то
    же самое, что нулевой zi для чисто FIR-фильтра, у которого нет скрытого
    состояния сверх этого окна). sliding_window_view(extended, ntaps) даёт
    вью (без копирования) со всеми такими окнами; децимация — это просто
    strided-срез этих окон перед умножением на taps, а не после фильтрации
    всех подряд.
    """

    def __init__(
        self, factor: int, cutoff_hz: float, input_sample_rate_hz: float, num_taps: int
    ) -> None:
        if factor < 1:
            raise ValueError(f"factor={factor} must be >= 1")
        self._factor = factor
        self._taps = firwin(num_taps, cutoff_hz, fs=input_sample_rate_hz).astype(np.float64)
        self._taps_reversed = self._taps[::-1].copy()
        # numpy сильно проседает на матмуле со смешанными dtype (например
        # complex64 @ float64 — падает в generic-цикл вместо BLAS, в разы
        # медленнее complex64 @ complex64) — держим taps ещё и в dtype входа,
        # лениво по факту первого вызова с этим dtype.
        self._taps_reversed_by_dtype: dict[np.dtype, np.ndarray] = {}
        self._history: np.ndarray | None = None  # последние (num_taps-1) реальных отсчётов
        self._phase = 0  # сколько отфильтрованных отсчётов накоплено с последнего взятого

    def process(self, x: np.ndarray) -> np.ndarray:
        if x.size == 0:
            return np.empty(0, dtype=x.dtype)

        history_len = self._taps.shape[0] - 1
        if self._history is None:
            self._history = np.zeros(history_len, dtype=x.dtype)

        extended = np.concatenate((self._history, x))
        if history_len > 0:
            self._history = extended[-history_len:].copy()

        taps_reversed = self._taps_reversed_by_dtype.get(x.dtype)
        if taps_reversed is None:
            taps_reversed = self._taps_reversed.astype(x.dtype)
            self._taps_reversed_by_dtype[x.dtype] = taps_reversed

        windows = np.lib.stride_tricks.sliding_window_view(extended, self._taps.shape[0])
        offset = (-self._phase) % self._factor
        # sliding_window_view даёт перекрывающийся (не C-contiguous) массив —
        # matmul на нём проваливается в медленный generic-путь numpy в разы
        # медленнее BLAS. Явная копия в contiguous перед matmul — на порядок
        # быстрее суммарно, чем матмул сразу на strided-вью (измерено).
        selected = np.ascontiguousarray(windows[offset :: self._factor])
        decimated = selected @ taps_reversed
        self._phase = (self._phase + x.shape[0]) % self._factor

        return decimated.astype(x.dtype)
