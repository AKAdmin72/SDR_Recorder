import queue
from datetime import datetime, timezone

import numpy as np
import pytest

from sdr_monitor.acquisition.iq_stream import IQStreamReader, convert_raw_iq_to_complex64
from sdr_monitor.config.acquisition_config import AcquisitionConfig
from sdr_monitor.config.radio_config import RadioConfig
from sdr_monitor.hardware.sample_format import SampleFormat

_RADIO_CONFIG = RadioConfig(
    center_frequency_hz=128_000_000,
    sample_rate_hz=2_000_000,
    settle_time_s=0.0,
)


class _FakeDevice:
    """Минимальная заглушка SdrDevice — IQStreamReader обращается к device
    только в start()/stop(), которые в этих тестах не вызываются напрямую."""

    sample_format = SampleFormat.INT8


def _make_reader(queue_max_blocks: int = 4, radio_config: RadioConfig = _RADIO_CONFIG) -> IQStreamReader:
    reader = IQStreamReader(
        device=_FakeDevice(),
        radio_config=radio_config,
        acquisition_config=AcquisitionConfig(
            queue_max_blocks=queue_max_blocks, stats_log_interval_s=1.0
        ),
    )
    reader._stream_start_utc = datetime.now(timezone.utc)
    return reader


def test_convert_raw_iq_to_complex64_int8_known_values():
    raw = np.array([64, -32, 0, 127, -128, 1], dtype=np.int8).view(np.uint8)

    result = convert_raw_iq_to_complex64(raw, SampleFormat.INT8)

    expected = np.array(
        [64 / 128 - 32j / 128, 0 + 127j / 128, -128 / 128 + 1j / 128],
        dtype=np.complex64,
    )
    np.testing.assert_allclose(result, expected, atol=1e-6)


def test_convert_raw_iq_to_complex64_uint8_known_values():
    raw = np.array([255, 0, 127, 128], dtype=np.uint8)

    result = convert_raw_iq_to_complex64(raw, SampleFormat.UINT8)

    expected = np.array(
        [(255 - 127.5) / 127.5 + (0 - 127.5) / 127.5 * 1j],
        dtype=np.complex64,
    )
    np.testing.assert_allclose(result[:1], expected, atol=1e-6)
    # RTL-SDR midpoint (127/128, оба близко к 127.5) должен давать почти-ноль
    assert abs(result[1]) < 0.02


def test_on_samples_builds_block_and_advances_sample_index():
    reader = _make_reader()
    raw_bytes = np.array([10, 20, 30, 40], dtype=np.int8).view(np.uint8)

    reader._on_samples(raw_bytes)

    assert reader.received_blocks == 1
    assert reader.received_samples == 2

    first_block = reader.get_block(timeout=0)
    assert first_block.sample_index == 0
    assert first_block.samples.shape == (2,)

    reader._on_samples(raw_bytes)
    second_block = reader.get_block(timeout=0)
    assert second_block.sample_index == 2


def test_on_samples_drops_block_when_queue_full():
    reader = _make_reader(queue_max_blocks=1)
    raw_bytes = np.array([1, 2], dtype=np.int8).view(np.uint8)

    reader._on_samples(raw_bytes)
    reader._on_samples(raw_bytes)

    assert reader.received_blocks == 2
    assert reader.dropped_blocks == 1


def test_on_samples_truncates_odd_length():
    reader = _make_reader()
    raw_bytes = np.array([1, 2, 3], dtype=np.int8).view(np.uint8)

    reader._on_samples(raw_bytes)

    block = reader.get_block(timeout=0)
    assert block.samples.shape == (1,)


def test_blocks_within_settle_window_are_discarded_not_enqueued():
    settling_config = RadioConfig(
        center_frequency_hz=128_000_000,
        sample_rate_hz=2_000_000,
        settle_time_s=0.000001,  # 2 отсчёта при 2_000_000 Гц
    )
    reader = _make_reader(radio_config=settling_config)
    raw_bytes = np.array([1, 2, 3, 4], dtype=np.int8).view(np.uint8)  # 2 комплексных отсчёта

    reader._on_samples(raw_bytes)

    assert reader.received_blocks == 1  # физически принят и учтён
    assert reader.discarded_settle_blocks == 1
    with pytest.raises(queue.Empty):
        reader.get_block(timeout=0)  # но потребителю не отдан

    # следующий блок уже за пределами окна устаканивания -> доходит до очереди
    reader._on_samples(raw_bytes)
    block = reader.get_block(timeout=0)
    assert block.sample_index == 2
    assert reader.discarded_settle_blocks == 1
