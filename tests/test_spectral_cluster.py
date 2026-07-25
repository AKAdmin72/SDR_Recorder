from datetime import datetime, timezone

import numpy as np
import pytest

from sdr_monitor.detection.spectral_cluster import find_clusters
from sdr_monitor.dsp.spectral_frame import SpectralFrame


def _make_frame(power_db_values: list[float]) -> SpectralFrame:
    power_db = np.asarray(power_db_values, dtype=np.float32)
    freqs = np.arange(power_db.shape[0], dtype=np.float64) * 1000.0  # 1 бин = 1 кГц
    return SpectralFrame(
        frequencies_hz=freqs,
        power_db=power_db,
        start_sample_index=0,
        end_sample_index=1000,
        sample_rate_hz=1000,
        stream_start_utc=datetime.now(timezone.utc),
    )


def test_no_clusters_when_all_below_threshold():
    frame = _make_frame([-100.0] * 10)
    noise_floor = np.full(10, -100.0, dtype=np.float32)

    assert find_clusters(frame, noise_floor, threshold_db=10.0, min_bandwidth_bins=1) == []


def test_single_cluster_detected_with_centroid_frequency():
    power_db = [-100.0, -100.0, -50.0, -50.0, -100.0, -100.0]
    frame = _make_frame(power_db)
    noise_floor = np.full(6, -100.0, dtype=np.float32)

    clusters = find_clusters(frame, noise_floor, threshold_db=10.0, min_bandwidth_bins=1)

    assert len(clusters) == 1
    cluster = clusters[0]
    assert cluster.peak_power_db == pytest.approx(-50.0)
    assert cluster.peak_snr_db == pytest.approx(50.0)
    # одинаковая мощность в бинах 2 и 3 -> центроид ровно посередине
    assert cluster.center_frequency_hz == pytest.approx(2500.0, abs=1.0)


def test_short_run_filtered_by_min_bandwidth():
    power_db = [-100.0, -50.0, -100.0]
    frame = _make_frame(power_db)
    noise_floor = np.full(3, -100.0, dtype=np.float32)

    assert find_clusters(frame, noise_floor, threshold_db=10.0, min_bandwidth_bins=2) == []
    assert len(find_clusters(frame, noise_floor, threshold_db=10.0, min_bandwidth_bins=1)) == 1


def test_two_separate_clusters_detected_independently():
    power_db = [-100.0, -50.0, -50.0, -100.0, -100.0, -40.0, -40.0, -100.0]
    frame = _make_frame(power_db)
    noise_floor = np.full(8, -100.0, dtype=np.float32)

    clusters = find_clusters(frame, noise_floor, threshold_db=10.0, min_bandwidth_bins=2)

    assert len(clusters) == 2
    assert clusters[0].peak_power_db == pytest.approx(-50.0)
    assert clusters[1].peak_power_db == pytest.approx(-40.0)


def test_run_touching_array_edges_is_detected():
    power_db = [-50.0, -50.0, -100.0, -100.0, -50.0, -50.0]
    frame = _make_frame(power_db)
    noise_floor = np.full(6, -100.0, dtype=np.float32)

    clusters = find_clusters(frame, noise_floor, threshold_db=10.0, min_bandwidth_bins=2)

    assert len(clusters) == 2


def test_excluded_mask_suppresses_cluster_entirely():
    power_db = [-100.0, -50.0, -50.0, -100.0]
    frame = _make_frame(power_db)
    noise_floor = np.full(4, -100.0, dtype=np.float32)
    excluded_mask = np.array([False, True, True, False])

    clusters = find_clusters(
        frame, noise_floor, threshold_db=10.0, min_bandwidth_bins=1, excluded_mask=excluded_mask
    )

    assert clusters == []


def test_excluded_mask_leaves_other_clusters_untouched():
    power_db = [-100.0, -50.0, -100.0, -100.0, -40.0, -100.0]
    frame = _make_frame(power_db)
    noise_floor = np.full(6, -100.0, dtype=np.float32)
    excluded_mask = np.array([False, True, False, False, False, False])

    clusters = find_clusters(
        frame, noise_floor, threshold_db=10.0, min_bandwidth_bins=1, excluded_mask=excluded_mask
    )

    assert len(clusters) == 1
    assert clusters[0].peak_power_db == pytest.approx(-40.0)
