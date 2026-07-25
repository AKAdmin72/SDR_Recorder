from datetime import datetime, timezone

import numpy as np
import pytest

from sdr_monitor.acquisition.iq_block import IQBlock
from sdr_monitor.config.fft_config import FFTConfig
from sdr_monitor.config.radio_config import RadioConfig
from sdr_monitor.dsp.fft_processor import FFTProcessor

_SAMPLE_RATE_HZ = 2_000_000
_CENTER_FREQ_HZ = 128_000_000


def _radio_config(**overrides) -> RadioConfig:
    defaults = dict(
        center_frequency_hz=_CENTER_FREQ_HZ,
        sample_rate_hz=_SAMPLE_RATE_HZ,
        settle_time_s=0.0,
    )
    defaults.update(overrides)
    return RadioConfig(**defaults)


def _fft_config(**overrides) -> FFTConfig:
    defaults = dict(fft_size=1024, window_type="hann", averaging_count=1, dc_notch_bins=0)
    defaults.update(overrides)
    return FFTConfig(**defaults)


def _make_block(samples: np.ndarray, sample_index: int, stream_start=None) -> IQBlock:
    return IQBlock(
        samples=samples.astype(np.complex64),
        sample_index=sample_index,
        sample_rate_hz=_SAMPLE_RATE_HZ,
        stream_start_utc=stream_start or datetime.now(timezone.utc),
    )


def test_tone_peak_lands_at_expected_bin():
    fft_size = 1024
    processor = FFTProcessor(_radio_config(), _fft_config(fft_size=fft_size))

    bin_offset = 100
    freq_offset_hz = bin_offset * _SAMPLE_RATE_HZ / fft_size
    n = np.arange(fft_size)
    tone = np.exp(2j * np.pi * freq_offset_hz * n / _SAMPLE_RATE_HZ).astype(np.complex64)

    frames = processor.process(_make_block(tone, sample_index=0))

    assert len(frames) == 1
    frame = frames[0]
    peak_index = int(np.argmax(frame.power_db))
    expected_index = fft_size // 2 + bin_offset
    assert peak_index == expected_index
    assert frame.frequencies_hz[peak_index] == pytest.approx(
        _CENTER_FREQ_HZ + freq_offset_hz, abs=1.0
    )


def test_averaging_uses_linear_power_not_db():
    fft_size = 64
    bin_offset = 5
    freq_offset_hz = bin_offset * _SAMPLE_RATE_HZ / fft_size
    n = np.arange(fft_size)
    silence = np.zeros(fft_size, dtype=np.complex64)
    loud_tone = (4.0 * np.exp(2j * np.pi * freq_offset_hz * n / _SAMPLE_RATE_HZ)).astype(
        np.complex64
    )

    averaged_processor = FFTProcessor(
        _radio_config(),
        _fft_config(fft_size=fft_size, averaging_count=2, window_type="rectangular"),
    )
    assert averaged_processor.process(_make_block(silence, sample_index=0)) == []
    frames = averaged_processor.process(_make_block(loud_tone, sample_index=fft_size))
    assert len(frames) == 1

    single_processor = FFTProcessor(
        _radio_config(),
        _fft_config(fft_size=fft_size, averaging_count=1, window_type="rectangular"),
    )
    single_frames = single_processor.process(_make_block(loud_tone, sample_index=0))

    peak_index = fft_size // 2 + bin_offset
    loud_only_db = single_frames[0].power_db[peak_index]

    # Усреднение линейной мощности loud-окна с нулевой мощностью silence-окна
    # вдвое снижает мощность в среднем -> -10*log10(2) дБ, а не среднее
    # арифметическое дБ (это была бы другая, неверная величина).
    assert frames[0].power_db[peak_index] == pytest.approx(
        loud_only_db - 10 * np.log10(2), abs=0.05
    )


def test_leftover_samples_carried_across_blocks():
    fft_size = 64
    processor = FFTProcessor(_radio_config(), _fft_config(fft_size=fft_size, averaging_count=1))

    rng_a = np.random.default_rng(0)
    rng_b = np.random.default_rng(1)
    samples_a = (rng_a.normal(size=40) + 1j * rng_a.normal(size=40)).astype(np.complex64)
    samples_b = (rng_b.normal(size=24) + 1j * rng_b.normal(size=24)).astype(np.complex64)

    frames = processor.process(_make_block(samples_a, sample_index=1000))
    assert frames == []  # 40 < fft_size=64, уходит в хвостовой буфер

    frames = processor.process(_make_block(samples_b, sample_index=1040))
    assert len(frames) == 1
    assert frames[0].start_sample_index == 1000
    assert frames[0].end_sample_index == 1000 + fft_size


def test_dc_notch_suppresses_center_bins():
    fft_size = 64
    processor = FFTProcessor(
        _radio_config(), _fft_config(fft_size=fft_size, averaging_count=1, dc_notch_bins=2)
    )
    dc_signal = np.full(fft_size, 3.0, dtype=np.complex64)

    frames = processor.process(_make_block(dc_signal, sample_index=0))

    center = fft_size // 2
    notched = frames[0].power_db[center - 2 : center + 3]
    assert np.all(notched < -190)  # соответствует уровню _POWER_FLOOR


def test_discontinuity_resets_pending_state():
    fft_size = 64
    processor = FFTProcessor(_radio_config(), _fft_config(fft_size=fft_size, averaging_count=1))

    short_block = np.zeros(10, dtype=np.complex64)
    assert processor.process(_make_block(short_block, sample_index=0)) == []

    gapped_block = np.zeros(fft_size, dtype=np.complex64)
    frames = processor.process(_make_block(gapped_block, sample_index=5000))

    assert len(frames) == 1
    assert frames[0].start_sample_index == 5000
