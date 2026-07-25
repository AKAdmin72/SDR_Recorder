"""Структурный протокол, за которым IQStreamReader не видит конкретное железо."""

from __future__ import annotations

from typing import Callable, Protocol

import numpy as np

from sdr_monitor.hardware.sample_format import SampleFormat


class SdrDevice(Protocol):
    """Минимальный интерфейс устройства, достаточный для IQStreamReader.

    `callback`, переданный в start_rx, получает уже развёрнутые из
    ABI-специфичной обёртки сырые межканальные байты (I0,Q0,I1,Q1,...) —
    вся специфика конкретного железа (структура native-callback, формат
    сэмплов) остаётся внутри реализации устройства.
    """

    sample_format: SampleFormat

    def start_rx(self, callback: Callable[[np.ndarray], None]) -> None: ...

    def stop_rx(self) -> None: ...

    def is_streaming(self) -> bool: ...
