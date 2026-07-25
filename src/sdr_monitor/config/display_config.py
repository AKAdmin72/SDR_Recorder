"""Параметры отображения (GUI)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DisplayConfig:
    """Настройки живого окна отображения обнаруженных передач."""

    refresh_interval_s: float
    queue_pump_interval_s: float

    # Максимум IQBlock-ов, обрабатываемых за один вызов _pump() (MonitorWindow).
    # Tk однопоточен — пока _pump() не вернул управление, окно не перерисуется
    # и не отреагирует ни на одну кнопку. Без ограничения при скоплении блоков
    # в очереди (например, во время активной записи, когда обработка блока
    # заметно дороже) _pump() мог бы вычерпывать её сколь угодно долго.
    max_blocks_per_pump_tick: int

    history_size: int
    spectrum_y_margin_db: float

    def __post_init__(self) -> None:
        if self.refresh_interval_s <= 0:
            raise ValueError(f"refresh_interval_s={self.refresh_interval_s} must be > 0")
        if self.queue_pump_interval_s <= 0:
            raise ValueError(
                f"queue_pump_interval_s={self.queue_pump_interval_s} must be > 0"
            )
        if self.max_blocks_per_pump_tick < 1:
            raise ValueError(
                f"max_blocks_per_pump_tick={self.max_blocks_per_pump_tick} must be >= 1"
            )
        if self.history_size < 1:
            raise ValueError(f"history_size={self.history_size} must be >= 1")
        if self.spectrum_y_margin_db < 0:
            raise ValueError(
                f"spectrum_y_margin_db={self.spectrum_y_margin_db} must be >= 0"
            )
