from pathlib import Path

import pytest

from sdr_monitor.config.config_loader import load_config

_COMMON_SECTIONS = """
[fft]
fft_size = 2048
window_type = "hann"
averaging_count = 8
dc_notch_bins = 2

[noise_floor]
window_seconds = 10.0
update_interval_s = 1.0
percentile = 10.0
warmup_seconds = 3.0

[detection]
open_threshold_db = 10.0
close_threshold_db = 6.0
min_bandwidth_bins = 3
open_confirm_frames = 3
close_confirm_frames = 15
frequency_match_tolerance_hz = 3000.0

[display]
refresh_interval_s = 0.5
queue_pump_interval_s = 0.05
max_blocks_per_pump_tick = 4
history_size = 20
spectrum_y_margin_db = 5.0

[audio]
channel_half_bandwidth_hz = 8000.0
channel_intermediate_sample_rate_hz = 80_000
channel_filter_taps = 127
modulation_type = "am"
fm_deviation_hz = 5000.0
voice_band_low_hz = 300.0
voice_band_high_hz = 3400.0
voice_filter_order = 4
audio_sample_rate_hz = 16_000
audio_resample_cutoff_hz = 7000.0
audio_resample_filter_taps = 127
am_pcm_full_scale_input = 0.05
fm_pcm_full_scale_input = 1.1
recordings_dir = "recordings"
min_recording_duration_s = 1.0
post_roll_duration_s = 0.5

[acquisition]
queue_max_blocks = 64
stats_log_interval_s = 5.0

[logging]
level = "INFO"
"""

_HACKRF_RADIO_TOML = """
[sdr]
type = "hackrf"

[radio.hackrf]
center_frequency_hz = 128_000_000
sample_rate_hz = 2_000_000
lna_gain_db = 24
vga_gain_db = 20
amp_enable = false
settle_time_s = 5.0
"""

_RTLSDR_RADIO_TOML = """
[sdr]
type = "rtlsdr"

[radio.rtlsdr]
center_frequency_hz = 126_900_000
sample_rate_hz = 2_048_000
gain_db = 40.2
agc_enabled = false
freq_correction_ppm = 0
settle_time_s = 2.0
read_async_buffer_count = 15
read_async_buffer_length = 262_144
"""

_VALID_TOML = _HACKRF_RADIO_TOML + _COMMON_SECTIONS


def test_loads_valid_config(tmp_path: Path):
    config_path = tmp_path / "app_config.toml"
    config_path.write_text(_VALID_TOML, encoding="utf-8")

    config = load_config(config_path)

    assert config.radio.center_frequency_hz == 128_000_000
    assert config.acquisition.queue_max_blocks == 64
    assert config.logging.level == "INFO"
    assert config.detection.blacklisted_ranges == ()
    assert config.audio.audio_sample_rate_hz == 16_000
    assert config.audio.recordings_dir == Path("recordings")


def test_loads_rtlsdr_config(tmp_path: Path):
    config_path = tmp_path / "app_config.toml"
    config_path.write_text(_RTLSDR_RADIO_TOML + _COMMON_SECTIONS, encoding="utf-8")

    config = load_config(config_path)

    assert config.radio.center_frequency_hz == 126_900_000
    assert config.radio.sample_rate_hz == 2_048_000
    assert config.radio.gain_db == 40.2


def test_ignores_unused_radio_section(tmp_path: Path):
    # Обе секции [radio.hackrf]/[radio.rtlsdr] могут присутствовать
    # одновременно — используется только та, что совпадает с sdr.type.
    config_path = tmp_path / "app_config.toml"
    config_path.write_text(
        _HACKRF_RADIO_TOML
        + "\n[radio.rtlsdr]\ncenter_frequency_hz = 1\nsample_rate_hz = 1\n"
        "gain_db = 1\nagc_enabled = true\nfreq_correction_ppm = 0\nsettle_time_s = 0\n"
        "read_async_buffer_count = 1\nread_async_buffer_length = 512\n"
        + _COMMON_SECTIONS,
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.radio.center_frequency_hz == 128_000_000


def test_unknown_sdr_type_raises(tmp_path: Path):
    config_path = tmp_path / "app_config.toml"
    config_path.write_text(
        "[sdr]\ntype = \"unknown\"\n" + _COMMON_SECTIONS, encoding="utf-8"
    )

    with pytest.raises(ValueError):
        load_config(config_path)


def test_loads_blacklisted_ranges(tmp_path: Path):
    config_path = tmp_path / "app_config.toml"
    config_path.write_text(
        _VALID_TOML
        + "\n[[detection.blacklisted_ranges]]\nstart_hz = 125_900_000\nend_hz = 126_250_000\n",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert len(config.detection.blacklisted_ranges) == 1
    assert config.detection.blacklisted_ranges[0].start_hz == 125_900_000
    assert config.detection.blacklisted_ranges[0].end_hz == 126_250_000


def test_missing_section_raises(tmp_path: Path):
    config_path = tmp_path / "app_config.toml"
    config_path.write_text("[sdr]\ntype = \"hackrf\"\n", encoding="utf-8")

    with pytest.raises(ValueError):
        load_config(config_path)


def test_repo_default_config_is_valid():
    # center_frequency_hz/modulation_type/blacklisted_ranges — рабочие
    # параметры, которые меняются напрямую в config/app_config.toml по ходу
    # тестов на реальном железе (см. историю правок), поэтому здесь
    # проверяется только структурная валидность файла, а не конкретная
    # текущая настройка.
    default_config_path = (
        Path(__file__).resolve().parents[1] / "config" / "app_config.toml"
    )
    config = load_config(default_config_path)
    assert config.radio.center_frequency_hz > 0
    assert config.audio.modulation_type in ("am", "fm")
    assert len(config.detection.blacklisted_ranges) >= 1
    for frequency_range in config.detection.blacklisted_ranges:
        assert frequency_range.end_hz > frequency_range.start_hz
