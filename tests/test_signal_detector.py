from datetime import datetime, timezone

import numpy as np
import pytest

from sdr_monitor.config.detection_config import DetectionConfig
from sdr_monitor.config.frequency_range import FrequencyRange
from sdr_monitor.detection.signal_detector import SignalDetector
from sdr_monitor.dsp.spectral_frame import SpectralFrame

_BIN_COUNT = 10
_SAMPLES_PER_FRAME = 1000
_SAMPLE_RATE_HZ = 1000  # 1 кадр = 1000 отсчётов = ровно 1.0 секунда
_STREAM_START = datetime(2026, 1, 1, tzinfo=timezone.utc)
_NOISE_FLOOR = np.full(_BIN_COUNT, -100.0, dtype=np.float32)


def _detection_config(**overrides) -> DetectionConfig:
    defaults = dict(
        open_threshold_db=10.0,
        close_threshold_db=5.0,
        min_bandwidth_bins=1,
        open_confirm_frames=2,
        close_confirm_frames=2,
        frequency_match_tolerance_hz=1500.0,
    )
    defaults.update(overrides)
    return DetectionConfig(**defaults)


def _quiet_power() -> list[float]:
    return [-100.0] * _BIN_COUNT


def _power_with_signal(level_db: float, bin_index: int = 4) -> list[float]:
    power = _quiet_power()
    power[bin_index] = level_db
    return power


def _make_frame(power_db_values: list[float], frame_number: int) -> SpectralFrame:
    power_db = np.asarray(power_db_values, dtype=np.float32)
    freqs = np.arange(_BIN_COUNT, dtype=np.float64) * 1000.0
    start = frame_number * _SAMPLES_PER_FRAME
    return SpectralFrame(
        frequencies_hz=freqs,
        power_db=power_db,
        start_sample_index=start,
        end_sample_index=start + _SAMPLES_PER_FRAME,
        sample_rate_hz=_SAMPLE_RATE_HZ,
        stream_start_utc=_STREAM_START,
    )


def test_full_lifecycle_open_hold_dip_close():
    detector = SignalDetector(_detection_config())

    assert detector.update(_make_frame(_power_with_signal(-85.0), 0), _NOISE_FLOOR) == []
    assert detector.update(_make_frame(_power_with_signal(-85.0), 1), _NOISE_FLOOR) == []
    # провал огибающей, но всё ещё выше close_threshold_db=5 (SNR=7) -> трек держится
    assert detector.update(_make_frame(_power_with_signal(-93.0), 2), _NOISE_FLOOR) == []
    assert detector.update(_make_frame(_power_with_signal(-85.0), 3), _NOISE_FLOOR) == []
    assert detector.update(_make_frame(_quiet_power(), 4), _NOISE_FLOOR) == []  # miss 1
    finalized = detector.update(_make_frame(_quiet_power(), 5), _NOISE_FLOOR)  # miss 2 -> закрытие

    assert len(finalized) == 1
    signal = finalized[0]
    assert signal.center_frequency_hz == pytest.approx(4000.0)
    assert signal.peak_level_db == pytest.approx(-85.0)
    assert signal.peak_snr_db == pytest.approx(15.0)
    assert (signal.start_time_utc - _STREAM_START).total_seconds() == pytest.approx(0.0)
    assert (signal.end_time_utc - _STREAM_START).total_seconds() == pytest.approx(4.0)
    assert signal.duration_s == pytest.approx(4.0)


def test_single_noisy_spike_never_confirms():
    detector = SignalDetector(_detection_config(open_confirm_frames=3))

    assert detector.update(_make_frame(_power_with_signal(-85.0), 0), _NOISE_FLOOR) == []
    assert detector.update(_make_frame(_quiet_power(), 1), _NOISE_FLOOR) == []

    assert detector.flush() == []


def test_provisional_progress_resets_on_single_miss():
    detector = SignalDetector(_detection_config(open_confirm_frames=3))

    detector.update(_make_frame(_power_with_signal(-85.0), 0), _NOISE_FLOOR)  # hit 1
    detector.update(_make_frame(_quiet_power(), 1), _NOISE_FLOOR)  # miss -> отброшен
    detector.update(_make_frame(_power_with_signal(-85.0), 2), _NOISE_FLOOR)  # новый трек, hit 1
    detector.update(_make_frame(_power_with_signal(-85.0), 3), _NOISE_FLOOR)  # hit 2 (нужно 3)

    # только 2 из требуемых 3 последовательных попаданий -> всё ещё PROVISIONAL
    assert detector.flush() == []


def test_flush_finalizes_ongoing_confirmed_track():
    detector = SignalDetector(_detection_config())

    detector.update(_make_frame(_power_with_signal(-85.0), 0), _NOISE_FLOOR)
    detector.update(_make_frame(_power_with_signal(-85.0), 1), _NOISE_FLOOR)  # CONFIRMED

    finalized = detector.flush()

    assert len(finalized) == 1
    assert finalized[0].duration_s == pytest.approx(2.0)
    assert detector.flush() == []  # треков больше нет, повторно ничего не репортит


def test_two_simultaneous_signals_tracked_independently():
    detector = SignalDetector(_detection_config())

    def _two_signal_power() -> list[float]:
        power = _quiet_power()
        power[2] = -85.0
        power[8] = -80.0
        return power

    detector.update(_make_frame(_two_signal_power(), 0), _NOISE_FLOOR)
    detector.update(_make_frame(_two_signal_power(), 1), _NOISE_FLOOR)  # оба CONFIRMED

    finalized = detector.flush()

    assert len(finalized) == 2
    frequencies = sorted(signal.center_frequency_hz for signal in finalized)
    assert frequencies == [pytest.approx(2000.0), pytest.approx(8000.0)]


def test_active_signals_empty_while_only_provisional():
    detector = SignalDetector(_detection_config(open_confirm_frames=2))

    detector.update(_make_frame(_power_with_signal(-85.0), 0), _NOISE_FLOOR)  # hit 1, PROVISIONAL

    assert detector.active_signals() == []


def test_active_signals_reflects_current_vs_peak_and_elapsed():
    detector = SignalDetector(_detection_config())

    detector.update(_make_frame(_power_with_signal(-85.0), 0), _NOISE_FLOOR)  # hit 1
    detector.update(_make_frame(_power_with_signal(-85.0), 1), _NOISE_FLOOR)  # CONFIRMED, peak=-85
    detector.update(_make_frame(_power_with_signal(-93.0), 2), _NOISE_FLOOR)  # провал в допуске close

    active = detector.active_signals()

    assert len(active) == 1
    signal = active[0]
    assert signal.center_frequency_hz == pytest.approx(4000.0)
    assert signal.current_level_db == pytest.approx(-93.0)  # текущий кадр
    assert signal.peak_level_db == pytest.approx(-85.0)  # максимум за трек
    assert signal.elapsed_s == pytest.approx(3.0)  # (frame2.end - frame0.start) / 1000


def test_track_id_stable_while_active_and_matches_finalized_signal():
    detector = SignalDetector(_detection_config())

    detector.update(_make_frame(_power_with_signal(-85.0), 0), _NOISE_FLOOR)
    detector.update(_make_frame(_power_with_signal(-85.0), 1), _NOISE_FLOOR)  # CONFIRMED

    active = detector.active_signals()
    assert len(active) == 1
    track_id = active[0].track_id

    active_again = detector.active_signals()
    assert active_again[0].track_id == track_id  # стабилен между вызовами

    detector.update(_make_frame(_quiet_power(), 2), _NOISE_FLOOR)  # miss 1
    finalized = detector.update(_make_frame(_quiet_power(), 3), _NOISE_FLOOR)  # miss 2 -> закрытие

    assert len(finalized) == 1
    assert finalized[0].track_id == track_id


def test_track_ids_unique_for_simultaneous_signals():
    detector = SignalDetector(_detection_config())

    def _two_signal_power() -> list[float]:
        power = _quiet_power()
        power[2] = -85.0
        power[8] = -80.0
        return power

    detector.update(_make_frame(_two_signal_power(), 0), _NOISE_FLOOR)
    detector.update(_make_frame(_two_signal_power(), 1), _NOISE_FLOOR)  # оба CONFIRMED

    active = detector.active_signals()
    track_ids = {signal.track_id for signal in active}
    assert len(track_ids) == 2


def test_blacklisted_range_never_confirms_track():
    # bin 4 -> 4000 Гц, попадает в чёрный список [3500, 4500)
    config = _detection_config(
        blacklisted_ranges=(FrequencyRange(start_hz=3500.0, end_hz=4500.0),)
    )
    detector = SignalDetector(config)

    for frame_number in range(10):
        finalized = detector.update(
            _make_frame(_power_with_signal(-85.0), frame_number), _NOISE_FLOOR
        )
        assert finalized == []

    assert detector.active_signals() == []
    assert detector.flush() == []


def test_signal_outside_blacklisted_range_still_detected():
    # чёрный список покрывает только бин 4 (4000 Гц), сигнал на бине 7 (7000 Гц) не затронут
    config = _detection_config(
        blacklisted_ranges=(FrequencyRange(start_hz=3500.0, end_hz=4500.0),)
    )
    detector = SignalDetector(config)

    detector.update(_make_frame(_power_with_signal(-85.0, bin_index=7), 0), _NOISE_FLOOR)
    detector.update(_make_frame(_power_with_signal(-85.0, bin_index=7), 1), _NOISE_FLOOR)

    finalized = detector.flush()
    assert len(finalized) == 1
    assert finalized[0].center_frequency_hz == pytest.approx(7000.0)


def test_active_signals_empty_after_close():
    detector = SignalDetector(_detection_config())

    detector.update(_make_frame(_power_with_signal(-85.0), 0), _NOISE_FLOOR)
    detector.update(_make_frame(_power_with_signal(-85.0), 1), _NOISE_FLOOR)  # CONFIRMED
    assert len(detector.active_signals()) == 1

    detector.update(_make_frame(_quiet_power(), 2), _NOISE_FLOOR)  # miss 1
    detector.update(_make_frame(_quiet_power(), 3), _NOISE_FLOOR)  # miss 2 -> закрыт

    assert detector.active_signals() == []
