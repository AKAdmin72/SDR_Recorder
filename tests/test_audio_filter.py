from pathlib import Path

import numpy as np
import pytest

from sdr_monitor.audio.audio_filter import AudioFilter
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


def test_removes_dc_offset():
    audio_config = _audio_config()
    filt = AudioFilter(audio_config, input_sample_rate_hz=audio_config.channel_intermediate_sample_rate_hz)

    out = filt.process(np.full(5000, 0.5, dtype=np.float32))

    steady = out[1000:]
    assert np.max(np.abs(steady)) < 0.01


def test_passes_voice_band_tone():
    audio_config = _audio_config()
    fs = audio_config.channel_intermediate_sample_rate_hz
    filt = AudioFilter(audio_config, input_sample_rate_hz=fs)

    n = 20000
    t = np.arange(n) / fs
    tone = np.sin(2 * np.pi * 1000.0 * t).astype(np.float32)

    out = filt.process(tone)

    steady = out[2000:]
    assert np.std(steady) > 0.3  # тон RMS ~0.707, полоса 300-3400Гц должна пропустить почти без потерь


def test_empty_input_returns_empty():
    audio_config = _audio_config()
    filt = AudioFilter(audio_config, input_sample_rate_hz=audio_config.channel_intermediate_sample_rate_hz)
    out = filt.process(np.empty(0, dtype=np.float32))
    assert out.shape[0] == 0
