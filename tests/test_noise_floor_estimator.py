from datetime import datetime, timezone

import numpy as np
import pytest

from sdr_monitor.config.noise_floor_config import NoiseFloorConfig
from sdr_monitor.dsp.noise_floor_estimator import NoiseFloorEstimator
from sdr_monitor.dsp.spectral_frame import SpectralFrame

_FRAME_DURATION_SAMPLES = 1000
_SAMPLE_RATE_HZ = 1000  # 1 отсчёт/Гц => длительность кадра ровно 1.0 секунда


def _make_frame(power_db_values: list[float], frame_number: int) -> SpectralFrame:
    power_db = np.asarray(power_db_values, dtype=np.float32)
    start = frame_number * _FRAME_DURATION_SAMPLES
    return SpectralFrame(
        frequencies_hz=np.zeros_like(power_db),
        power_db=power_db,
        start_sample_index=start,
        end_sample_index=start + _FRAME_DURATION_SAMPLES,
        sample_rate_hz=_SAMPLE_RATE_HZ,
        stream_start_utc=datetime.now(timezone.utc),
    )


def test_not_ready_before_warmup_frames():
    config = NoiseFloorConfig(
        window_seconds=10, update_interval_s=3, percentile=50, warmup_seconds=4
    )
    estimator = NoiseFloorEstimator(config)

    for i in range(3):
        estimator.update(_make_frame([-90.0], i))
        assert not estimator.is_ready

    estimator.update(_make_frame([-90.0], 3))
    assert estimator.is_ready


def test_noise_floor_db_raises_before_ready():
    config = NoiseFloorConfig(
        window_seconds=10, update_interval_s=3, percentile=50, warmup_seconds=4
    )
    estimator = NoiseFloorEstimator(config)

    with pytest.raises(RuntimeError):
        estimator.noise_floor_db()


def test_percentile_value_matches_numpy_after_warmup():
    config = NoiseFloorConfig(
        window_seconds=10, update_interval_s=1, percentile=50, warmup_seconds=4
    )
    estimator = NoiseFloorEstimator(config)

    values = [-90.0, -80.0, -70.0, -60.0]
    for i, value in enumerate(values):
        estimator.update(_make_frame([value], i))

    assert estimator.is_ready
    expected = np.percentile(values, 50)
    np.testing.assert_allclose(estimator.noise_floor_db(), [expected], atol=1e-4)


def test_recompute_only_happens_at_configured_interval():
    config = NoiseFloorConfig(
        window_seconds=10, update_interval_s=3, percentile=50, warmup_seconds=2
    )
    estimator = NoiseFloorEstimator(config)

    for i in range(2):
        estimator.update(_make_frame([-90.0], i))
    assert estimator.is_ready
    np.testing.assert_allclose(estimator.noise_floor_db(), [-90.0])

    for i in range(2, 4):
        estimator.update(_make_frame([-10.0], i))
        # интервал пересчёта - 3 кадра, ещё не набежало -> оценка не сдвинулась
        np.testing.assert_allclose(estimator.noise_floor_db(), [-90.0])

    estimator.update(_make_frame([-10.0], 4))
    np.testing.assert_allclose(estimator.noise_floor_db(), [-10.0])


def test_percentile_robust_to_intermittent_signal():
    config = NoiseFloorConfig(
        window_seconds=20, update_interval_s=1, percentile=10, warmup_seconds=20
    )
    estimator = NoiseFloorEstimator(config)

    rng = np.random.default_rng(42)
    baseline_db = -95.0
    signal_db = -30.0

    for i in range(20):
        # сигнал присутствует в 20% кадров - заметно меньше (100-percentile)=90%
        power = signal_db if i % 5 == 0 else baseline_db + rng.normal(scale=0.5)
        estimator.update(_make_frame([power], i))

    assert estimator.is_ready
    floor = estimator.noise_floor_db()[0]
    assert floor < baseline_db + 3.0
