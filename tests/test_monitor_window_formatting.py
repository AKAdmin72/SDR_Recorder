from datetime import datetime, timezone

import numpy as np

from sdr_monitor.detection.active_signal import ActiveSignal
from sdr_monitor.detection.detected_signal import DetectedSignal
from sdr_monitor.display.monitor_window import (
    _MaxHoldAccumulator,
    _dc_notch_mask,
    _format_active_row,
    _format_history_row,
    _format_time,
    _y_limits_with_margin,
)


def test_format_active_row():
    signal = ActiveSignal(
        track_id=1,
        center_frequency_hz=126_900_000.0,
        current_level_db=-32.456,
        current_snr_db=8.1,
        peak_level_db=-28.9,
        peak_snr_db=12.345,
        start_time_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
        elapsed_s=3.14159,
    )

    row = _format_active_row(signal)

    assert row == ("126.9000", "-32.5", "8.1", "-28.9", "12.3", "3.1")


def test_format_history_row():
    signal = DetectedSignal(
        track_id=1,
        center_frequency_hz=126_900_000.0,
        peak_level_db=-28.9,
        peak_snr_db=12.345,
        start_time_utc=datetime(2026, 1, 1, 10, 0, 0, 500_000, tzinfo=timezone.utc),
        end_time_utc=datetime(2026, 1, 1, 10, 0, 2, 750_000, tzinfo=timezone.utc),
        duration_s=2.25,
    )

    row = _format_history_row(signal)

    assert row == ("126.9000", "-28.9", "12.3", "10:00:00.500", "10:00:02.750", "2.250")


def test_format_time_truncates_to_milliseconds():
    value = datetime(2026, 1, 1, 12, 34, 56, 789_123, tzinfo=timezone.utc)

    assert _format_time(value) == "12:34:56.789"


def test_max_hold_accumulator_consume_without_update_returns_none():
    accumulator = _MaxHoldAccumulator()

    assert accumulator.consume() is None


def test_max_hold_accumulator_tracks_elementwise_maximum():
    accumulator = _MaxHoldAccumulator()

    accumulator.update(np.array([-90.0, -50.0, -70.0], dtype=np.float32))
    accumulator.update(np.array([-60.0, -55.0, -80.0], dtype=np.float32))

    result = accumulator.consume()

    np.testing.assert_allclose(result, [-60.0, -50.0, -70.0])


def test_max_hold_accumulator_resets_after_consume():
    accumulator = _MaxHoldAccumulator()
    accumulator.update(np.array([-90.0], dtype=np.float32))

    accumulator.consume()

    assert accumulator.consume() is None


def test_dc_notch_mask_excludes_notch_span():
    mask = _dc_notch_mask(bin_count=10, dc_notch_bins=2)

    # center = 10 // 2 = 5, обнулены бины 3,4,5,6,7
    assert list(mask) == [True, True, True, False, False, False, False, False, True, True]


def test_dc_notch_mask_no_notch_when_disabled():
    mask = _dc_notch_mask(bin_count=6, dc_notch_bins=0)

    assert mask.all()


def test_y_limits_with_margin_pads_both_sides():
    values = np.array([-90.0, -30.0, -60.0])

    limits = _y_limits_with_margin(values, margin_db=5.0)

    assert limits == (-95.0, -25.0)
