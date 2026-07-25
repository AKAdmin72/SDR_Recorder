"""Оконные функции для FFT-анализа."""

from __future__ import annotations

import numpy as np
from scipy.signal import windows as scipy_windows

_WINDOW_FACTORIES = {
    "hann": scipy_windows.hann,
    "hamming": scipy_windows.hamming,
    "blackmanharris": scipy_windows.blackmanharris,
    "rectangular": lambda size: np.ones(size, dtype=np.float64),
}


def get_window(window_type: str, size: int) -> np.ndarray:
    """Строит оконную функцию длины `size`. `window_type` уже провалидирован FFTConfig."""
    factory = _WINDOW_FACTORIES[window_type]
    return factory(size).astype(np.float32)
