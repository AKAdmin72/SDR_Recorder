from pathlib import Path
from types import SimpleNamespace

import pytest

from sdr_monitor.audio.am_demodulator import AmDemodulator
from sdr_monitor.audio.demodulator_factory import create_demodulator
from sdr_monitor.audio.fm_demodulator import FmDemodulator
from sdr_monitor.config.audio_config import AudioConfig


def _audio_config(**overrides) -> AudioConfig:
    defaults = dict(
        channel_half_bandwidth_hz=8000.0,
        channel_intermediate_sample_rate_hz=80_000,
        channel_filter_taps=127,
        modulation_type="am",
        fm_deviation_hz=5000.0,
        voice_band_low_hz=300.0,
        voice_band_high_hz=3400.0,
        voice_filter_order=4,
        audio_sample_rate_hz=16_000,
        audio_resample_cutoff_hz=7000.0,
        audio_resample_filter_taps=127,
        am_pcm_full_scale_input=0.05,
        fm_pcm_full_scale_input=1.1,
        recordings_dir=Path("recordings"),
        min_recording_duration_s=1.0,
        post_roll_duration_s=0.5,
    )
    defaults.update(overrides)
    return AudioConfig(**defaults)


def test_creates_am_demodulator_for_am_type():
    demod = create_demodulator(_audio_config(modulation_type="am"))
    assert isinstance(demod, AmDemodulator)


def test_creates_fm_demodulator_for_fm_type():
    demod = create_demodulator(
        _audio_config(modulation_type="fm", fm_deviation_hz=5000.0)
    )
    assert isinstance(demod, FmDemodulator)


def test_raises_for_unknown_modulation_type():
    # AudioConfig сам не пропустит невалидный modulation_type (валидация в
    # __post_init__) — используем заглушку с тем же полем, раз factory
    # обращается только к нему.
    fake_config = SimpleNamespace(modulation_type="usb")
    with pytest.raises(ValueError):
        create_demodulator(fake_config)
