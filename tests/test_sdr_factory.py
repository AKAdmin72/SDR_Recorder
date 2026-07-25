import pytest

from sdr_monitor.config.hackrf_radio_config import HackRFRadioConfig
from sdr_monitor.config.radio_config import RadioConfig
from sdr_monitor.config.rtlsdr_radio_config import RtlSdrRadioConfig
from sdr_monitor.hardware import sdr_factory

_HACKRF_CONFIG = HackRFRadioConfig(
    center_frequency_hz=128_000_000,
    sample_rate_hz=2_000_000,
    lna_gain_db=24,
    vga_gain_db=20,
    amp_enable=False,
    settle_time_s=5.0,
)

_RTLSDR_CONFIG = RtlSdrRadioConfig(
    center_frequency_hz=126_900_000,
    sample_rate_hz=2_048_000,
    gain_db=40.2,
    agc_enabled=False,
    freq_correction_ppm=0,
    settle_time_s=2.0,
    read_async_buffer_count=15,
    read_async_buffer_length=262_144,
)


class _FakeDevice:
    def __init__(self, radio_config):
        self.radio_config = radio_config


def test_creates_hackrf_device_for_hackrf_config(monkeypatch):
    # create_sdr_device не должен трогать реальное железо/DLL — только
    # выбирать класс по типу RadioConfig, поэтому конструкторы подменены.
    monkeypatch.setattr(sdr_factory, "HackRFDevice", _FakeDevice)
    device = sdr_factory.create_sdr_device(_HACKRF_CONFIG)
    assert isinstance(device, _FakeDevice)
    assert device.radio_config is _HACKRF_CONFIG


def test_creates_rtlsdr_device_for_rtlsdr_config(monkeypatch):
    monkeypatch.setattr(sdr_factory, "RtlSdrDevice", _FakeDevice)
    device = sdr_factory.create_sdr_device(_RTLSDR_CONFIG)
    assert isinstance(device, _FakeDevice)
    assert device.radio_config is _RTLSDR_CONFIG


def test_raises_for_unknown_radio_config_type():
    base_config = RadioConfig(
        center_frequency_hz=128_000_000, sample_rate_hz=2_000_000, settle_time_s=0.0
    )
    with pytest.raises(TypeError):
        sdr_factory.create_sdr_device(base_config)
