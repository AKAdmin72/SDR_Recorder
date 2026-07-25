"""Выбор конкретного класса устройства по типу RadioConfig из [sdr].type."""

from __future__ import annotations

from sdr_monitor.config.hackrf_radio_config import HackRFRadioConfig
from sdr_monitor.config.radio_config import RadioConfig
from sdr_monitor.config.rtlsdr_radio_config import RtlSdrRadioConfig
from sdr_monitor.hardware.hackrf_device import HackRFDevice
from sdr_monitor.hardware.rtlsdr_device import RtlSdrDevice


def create_sdr_device(radio_config: RadioConfig) -> HackRFDevice | RtlSdrDevice:
    """Создаёт (но не открывает — используйте как контекстный менеджер) устройство,
    соответствующее конкретному подклассу RadioConfig, построенному config_loader'ом
    из секции [sdr].type."""
    if isinstance(radio_config, HackRFRadioConfig):
        return HackRFDevice(radio_config)
    if isinstance(radio_config, RtlSdrRadioConfig):
        return RtlSdrDevice(radio_config)
    raise TypeError(f"Unknown RadioConfig type: {type(radio_config)!r}")
