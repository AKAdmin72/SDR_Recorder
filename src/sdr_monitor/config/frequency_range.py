"""Диапазон частот [start_hz, end_hz)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FrequencyRange:
    """Полуоткрытый интервал частот, Гц."""

    start_hz: float
    end_hz: float

    def __post_init__(self) -> None:
        if self.end_hz <= self.start_hz:
            raise ValueError(
                f"end_hz={self.end_hz} must be strictly greater than start_hz={self.start_hz}"
            )
