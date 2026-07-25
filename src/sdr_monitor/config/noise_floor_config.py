"""Параметры оценки шумового фона."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NoiseFloorConfig:
    """Настройки скользящей перцентильной оценки шумового пола по бинам."""

    window_seconds: float
    update_interval_s: float
    percentile: float
    warmup_seconds: float

    def __post_init__(self) -> None:
        if self.window_seconds <= 0:
            raise ValueError(f"window_seconds={self.window_seconds} must be > 0")
        if self.update_interval_s <= 0:
            raise ValueError(f"update_interval_s={self.update_interval_s} must be > 0")
        if not 0.0 < self.percentile < 100.0:
            raise ValueError(f"percentile={self.percentile} must be in (0, 100)")
        if self.warmup_seconds < 0:
            raise ValueError(f"warmup_seconds={self.warmup_seconds} must be >= 0")
        if self.warmup_seconds > self.window_seconds:
            raise ValueError(
                f"warmup_seconds={self.warmup_seconds} cannot exceed "
                f"window_seconds={self.window_seconds}"
            )
