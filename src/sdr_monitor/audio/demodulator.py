"""Структурный протокол демодулятора канала."""

from __future__ import annotations

from typing import Protocol

import numpy as np


class Demodulator(Protocol):
    """Минимальный интерфейс демодулятора: канал (I/Q на 0 Гц) -> аудио.

    Реализации могут быть как без состояния (AM), так и со состоянием между
    вызовами process() (FM — нужна непрерывность фазы на границе чанков).
    """

    def process(self, channel_samples: np.ndarray) -> np.ndarray: ...
