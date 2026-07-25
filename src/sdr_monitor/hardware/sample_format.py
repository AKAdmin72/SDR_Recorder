"""Формат кодирования сырых I/Q-байт на выходе конкретного SDR-устройства."""

from __future__ import annotations

import enum


class SampleFormat(enum.Enum):
    """Как физически закодирован один I- или Q-отсчёт в потоке сырых байт."""

    INT8 = "int8"  # знаковый, как у HackRF (libhackrf)
    UINT8 = "uint8"  # беззнаковый со смещением 127.5, как у RTL-SDR (librtlsdr)
