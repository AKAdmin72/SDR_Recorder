"""Параметры конвейера захвата IQ (очередь, статистика)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AcquisitionConfig:
    """Настройки буферизации и телеметрии потока IQ-блоков."""

    queue_max_blocks: int
    stats_log_interval_s: float

    def __post_init__(self) -> None:
        if self.queue_max_blocks < 1:
            raise ValueError(f"queue_max_blocks={self.queue_max_blocks} must be >= 1")
        if self.stats_log_interval_s <= 0:
            raise ValueError(
                f"stats_log_interval_s={self.stats_log_interval_s} must be > 0"
            )
