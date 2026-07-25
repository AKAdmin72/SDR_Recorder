from pathlib import Path

import numpy as np
import pytest

from sdr_monitor.audio.channel_extractor import ChannelExtractor
from sdr_monitor.config.audio_config import AudioConfig
from sdr_monitor.config.radio_config import RadioConfig


def _radio_config(**overrides) -> RadioConfig:
    defaults = dict(
        center_frequency_hz=126_600_000,
        sample_rate_hz=2_000_000,
        settle_time_s=5.0,
    )
    defaults.update(overrides)
    return RadioConfig(**defaults)


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


def test_rejects_non_integer_decimation_factor():
    radio = _radio_config(sample_rate_hz=2_000_000)
    audio = _audio_config(channel_intermediate_sample_rate_hz=77_000)
    with pytest.raises(ValueError):
        ChannelExtractor(radio, audio, channel_frequency_hz=126_600_000)


def test_shifts_channel_to_zero_and_decimates():
    radio = _radio_config()
    audio = _audio_config()
    offset_hz = 100_000.0
    extractor = ChannelExtractor(radio, audio, channel_frequency_hz=radio.center_frequency_hz + offset_hz)

    fs = radio.sample_rate_hz
    n = 20000
    t = np.arange(n) / fs
    tone = np.exp(2j * np.pi * offset_hz * t).astype(np.complex64)

    out = extractor.process(tone, sample_index=0)

    assert out.shape[0] == n // 25  # 2_000_000 / 80_000 = 25
    steady = out[50:]
    assert np.std(np.abs(steady)) < 0.05
    assert np.mean(np.abs(steady)) == pytest.approx(1.0, rel=0.1)


def test_split_processing_matches_single_call():
    radio = _radio_config()
    audio = _audio_config()
    offset_hz = 50_000.0
    channel_freq = radio.center_frequency_hz + offset_hz

    fs = radio.sample_rate_hz
    n = 5000
    t = np.arange(n) / fs
    tone = np.exp(2j * np.pi * offset_hz * t).astype(np.complex64)

    extractor_single = ChannelExtractor(radio, audio, channel_frequency_hz=channel_freq)
    out_single = extractor_single.process(tone, sample_index=1000)

    extractor_split = ChannelExtractor(radio, audio, channel_frequency_hz=channel_freq)
    out_a = extractor_split.process(tone[:2000], sample_index=1000)
    out_b = extractor_split.process(tone[2000:], sample_index=3000)
    out_combined = np.concatenate([out_a, out_b])

    np.testing.assert_allclose(out_combined, out_single, atol=1e-5)


def test_empty_input_returns_empty():
    radio = _radio_config()
    audio = _audio_config()
    extractor = ChannelExtractor(radio, audio, channel_frequency_hz=radio.center_frequency_hz)
    out = extractor.process(np.empty(0, dtype=np.complex64), sample_index=0)
    assert out.shape[0] == 0
