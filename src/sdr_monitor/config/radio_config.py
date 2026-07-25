"""Общие параметры радиотракта, не зависящие от конкретного SDR-железа."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RadioConfig:
    """Настройки одного непрерывного сеанса приёма, общие для любого SDR.

    Специфичные для конкретного железа параметры (усиление, AGC, коррекция
    частоты и т.п.) живут в подклассах — см. HackRFRadioConfig,
    RtlSdrRadioConfig. Модули выше границы приёма (FFTProcessor,
    RecordingManager, ChannelExtractor, MonitorWindow, IQStreamReader) знают
    только об этих трёх общих полях.
    """

    center_frequency_hz: int
    sample_rate_hz: int
    settle_time_s: float

    def __post_init__(self) -> None:
        if self.settle_time_s < 0:
            raise ValueError(f"settle_time_s={self.settle_time_s} must be >= 0")
