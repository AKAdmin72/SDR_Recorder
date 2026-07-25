from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from sdr_monitor.acquisition.iq_block import IQBlock
from sdr_monitor.audio.channel_recorder import ChannelRecorder, _build_file_path
from sdr_monitor.config.audio_config import AudioConfig
from sdr_monitor.config.radio_config import RadioConfig

_START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_build_file_path_format():
    path = _build_file_path(Path("recordings"), datetime(2026, 7, 12, 14, 31, 8, tzinfo=timezone.utc), 127_900_000.0)
    assert path == Path("recordings") / "2026-07-12_14-31-08_127900000.wav"


def test_build_file_path_rounds_frequency():
    path = _build_file_path(Path("recordings"), _START, 126_899_999.6)
    assert path.name == "2026-01-01_00-00-00_126900000.wav"


def _radio_config(**overrides) -> RadioConfig:
    defaults = dict(
        center_frequency_hz=126_600_000,
        sample_rate_hz=2_000_000,
        settle_time_s=5.0,
    )
    defaults.update(overrides)
    return RadioConfig(**defaults)


def _audio_config(recordings_dir: Path, **overrides) -> AudioConfig:
    defaults = dict(
        channel_half_bandwidth_hz=8000.0,
        channel_intermediate_sample_rate_hz=80_000,
        channel_filter_taps=63,
        modulation_type="am",
        fm_deviation_hz=5000.0,
        voice_band_low_hz=300.0,
        voice_band_high_hz=3400.0,
        voice_filter_order=4,
        audio_sample_rate_hz=16_000,
        audio_resample_cutoff_hz=7000.0,
        audio_resample_filter_taps=63,
        am_pcm_full_scale_input=1.0,
        fm_pcm_full_scale_input=1.0,
        recordings_dir=recordings_dir,
        min_recording_duration_s=1.0,
        post_roll_duration_s=0.5,
    )
    defaults.update(overrides)
    return AudioConfig(**defaults)


def _make_block(radio_config: RadioConfig, sample_index: int, n_samples: int) -> IQBlock:
    samples = np.full(n_samples, 0.1 + 0j, dtype=np.complex64)
    return IQBlock(
        samples=samples,
        sample_index=sample_index,
        sample_rate_hz=radio_config.sample_rate_hz,
        stream_start_utc=_START,
    )


def _make_recorder(tmp_path: Path, **audio_overrides) -> ChannelRecorder:
    radio = _radio_config()
    audio = _audio_config(tmp_path, **audio_overrides)
    return ChannelRecorder.create(
        audio, radio, track_id=1, center_frequency_hz=radio.center_frequency_hz, start_time_utc=_START
    )


def test_short_signal_never_creates_file(tmp_path):
    recorder = _make_recorder(tmp_path, min_recording_duration_s=10.0)

    recorder.process(_make_block(_radio_config(), 0, 200_000))  # ~0.1с аудио на выходе
    was_recorded = recorder.begin_closing()

    assert was_recorded is False
    assert recorder.is_done is True
    assert list(tmp_path.glob("*.wav")) == []


def test_long_signal_creates_file(tmp_path):
    recorder = _make_recorder(tmp_path, min_recording_duration_s=0.5, post_roll_duration_s=0.0)

    recorder.process(_make_block(_radio_config(), 0, 2_000_000))  # ~1с аудио на выходе
    assert recorder.is_done is False

    was_recorded = recorder.begin_closing()

    assert was_recorded is True
    assert recorder.is_done is True  # post_roll_duration_s=0.0 -> закрывается сразу
    assert len(list(tmp_path.glob("*.wav"))) == 1


def test_post_roll_keeps_recording_after_close(tmp_path):
    recorder = _make_recorder(tmp_path, min_recording_duration_s=0.1, post_roll_duration_s=0.2)
    radio = _radio_config()

    recorder.process(_make_block(radio, 0, 2_000_000))  # переход в RECORDING
    assert recorder.is_done is False

    was_recorded = recorder.begin_closing()
    assert was_recorded is True
    assert recorder.is_done is False  # нужно ещё 0.2с post-roll

    recorder.process(_make_block(radio, 2_000_000, 2_000_000))  # с запасом хватает на post-roll
    assert recorder.is_done is True


def test_close_immediately_discards_buffered_short_signal(tmp_path):
    recorder = _make_recorder(tmp_path, min_recording_duration_s=10.0)

    recorder.process(_make_block(_radio_config(), 0, 200_000))
    recorder.close_immediately()

    assert recorder.is_done is True
    assert list(tmp_path.glob("*.wav")) == []


def test_close_immediately_finalizes_open_file_without_full_post_roll(tmp_path):
    recorder = _make_recorder(tmp_path, min_recording_duration_s=0.1, post_roll_duration_s=5.0)
    radio = _radio_config()

    recorder.process(_make_block(radio, 0, 2_000_000))  # переход в RECORDING
    recorder.begin_closing()
    assert recorder.is_done is False  # post-roll 5с ещё не набран

    recorder.close_immediately()

    assert recorder.is_done is True
    assert len(list(tmp_path.glob("*.wav"))) == 1


def test_process_after_done_is_noop(tmp_path):
    recorder = _make_recorder(tmp_path, min_recording_duration_s=10.0)

    recorder.process(_make_block(_radio_config(), 0, 200_000))
    recorder.begin_closing()
    assert recorder.is_done is True

    recorder.process(_make_block(_radio_config(), 200_000, 200_000))  # не должно бросать
