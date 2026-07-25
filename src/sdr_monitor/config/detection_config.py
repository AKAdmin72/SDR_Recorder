"""Параметры детекции активных сигналов (порог + гистерезис)."""

from __future__ import annotations

from dataclasses import dataclass, field

from sdr_monitor.config.frequency_range import FrequencyRange


@dataclass(frozen=True, slots=True)
class DetectionConfig:
    """Настройки двухпорогового (гистерезисного) детектора передач."""

    open_threshold_db: float
    close_threshold_db: float
    min_bandwidth_bins: int
    open_confirm_frames: int
    close_confirm_frames: int
    frequency_match_tolerance_hz: float
    blacklisted_ranges: tuple[FrequencyRange, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.close_threshold_db >= self.open_threshold_db:
            raise ValueError(
                f"close_threshold_db={self.close_threshold_db} must be strictly less than "
                f"open_threshold_db={self.open_threshold_db} — otherwise there is no hysteresis"
            )
        if self.min_bandwidth_bins < 1:
            raise ValueError(f"min_bandwidth_bins={self.min_bandwidth_bins} must be >= 1")
        if self.open_confirm_frames < 1:
            raise ValueError(f"open_confirm_frames={self.open_confirm_frames} must be >= 1")
        if self.close_confirm_frames < 1:
            raise ValueError(f"close_confirm_frames={self.close_confirm_frames} must be >= 1")
        if self.frequency_match_tolerance_hz <= 0:
            raise ValueError(
                f"frequency_match_tolerance_hz={self.frequency_match_tolerance_hz} must be > 0"
            )
