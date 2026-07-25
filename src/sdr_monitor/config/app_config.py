"""Корневой конфиг приложения, объединяющий все секции."""

from __future__ import annotations

from dataclasses import dataclass

from sdr_monitor.config.acquisition_config import AcquisitionConfig
from sdr_monitor.config.audio_config import AudioConfig
from sdr_monitor.config.detection_config import DetectionConfig
from sdr_monitor.config.display_config import DisplayConfig
from sdr_monitor.config.fft_config import FFTConfig
from sdr_monitor.config.logging_config import LoggingConfig
from sdr_monitor.config.noise_floor_config import NoiseFloorConfig
from sdr_monitor.config.radio_config import RadioConfig


@dataclass(frozen=True, slots=True)
class AppConfig:
    # Конкретный подкласс (HackRFRadioConfig | RtlSdrRadioConfig) выбирается
    # в config_loader по [sdr].type.
    radio: RadioConfig
    acquisition: AcquisitionConfig
    fft: FFTConfig
    noise_floor: NoiseFloorConfig
    detection: DetectionConfig
    display: DisplayConfig
    audio: AudioConfig
    logging: LoggingConfig
