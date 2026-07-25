from pathlib import Path

import pytest

from sdr_monitor.config.audio_config import AudioConfig

_VALID_KWARGS = dict(
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


def test_accepts_valid_values():
    config = AudioConfig(**_VALID_KWARGS)
    assert config.audio_sample_rate_hz == 16_000


def test_pcm_full_scale_input_picks_active_modulation_type():
    am_config = AudioConfig(**{**_VALID_KWARGS, "modulation_type": "am"})
    fm_config = AudioConfig(**{**_VALID_KWARGS, "modulation_type": "fm"})

    assert am_config.pcm_full_scale_input == _VALID_KWARGS["am_pcm_full_scale_input"]
    assert fm_config.pcm_full_scale_input == _VALID_KWARGS["fm_pcm_full_scale_input"]


@pytest.mark.parametrize(
    "field,invalid_value",
    [
        ("channel_half_bandwidth_hz", 0.0),
        ("channel_half_bandwidth_hz", -100.0),
        ("channel_intermediate_sample_rate_hz", 15_000),  # < 2 * 8000
        ("channel_filter_taps", 2),
        ("modulation_type", "usb"),
        ("fm_deviation_hz", 0.0),
        ("fm_deviation_hz", -100.0),
        ("fm_deviation_hz", 40_000.0),  # >= половины intermediate rate (80_000/2)
        ("voice_band_low_hz", 0.0),
        ("voice_band_low_hz", 5000.0),  # >= voice_band_high_hz
        ("voice_band_high_hz", 45_000.0),  # >= половины intermediate rate
        ("voice_filter_order", 0),
        ("audio_sample_rate_hz", 0),
        ("audio_resample_cutoff_hz", 0.0),
        ("audio_resample_cutoff_hz", 9000.0),  # >= audio_sample_rate_hz/2
        ("audio_resample_filter_taps", 2),
        ("am_pcm_full_scale_input", 0.0),
        ("fm_pcm_full_scale_input", 0.0),
        ("min_recording_duration_s", -1.0),
        ("post_roll_duration_s", -1.0),
    ],
)
def test_rejects_invalid_values(field, invalid_value):
    kwargs = dict(_VALID_KWARGS)
    kwargs[field] = invalid_value
    with pytest.raises(ValueError):
        AudioConfig(**kwargs)
