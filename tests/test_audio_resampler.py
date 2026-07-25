from pathlib import Path

import numpy as np
import pytest

from sdr_monitor.audio.audio_resampler import AudioResampler
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


def test_rejects_non_integer_factor():
    # 80_000 / 15_000 = 5.33... - не целое; audio_resample_cutoff_hz=7000 всё ещё
    # валиден относительно audio_sample_rate_hz/2=7500, чтобы сработала именно
    # проверка AudioResampler, а не AudioConfig.__post_init__.
    audio_config = _audio_config(
        channel_intermediate_sample_rate_hz=80_000, audio_sample_rate_hz=15_000
    )
    with pytest.raises(ValueError):
        AudioResampler(audio_config)


def test_decimates_to_target_rate():
    audio_config = _audio_config()
    resampler = AudioResampler(audio_config)

    out = resampler.process(np.ones(1000, dtype=np.float32))

    assert out.shape[0] == 200  # 1000 / (80000/16000 = 5)
