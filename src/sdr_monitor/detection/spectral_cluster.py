"""Группировка бинов спектра, превысивших порог, в кандидаты-сигналы."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from sdr_monitor.dsp.spectral_frame import SpectralFrame


@dataclass(frozen=True, slots=True)
class SpectralCluster:
    """Одна связная группа бинов выше порога в одном спектральном кадре."""

    center_frequency_hz: float
    peak_power_db: float
    peak_snr_db: float


def find_clusters(
    frame: SpectralFrame,
    noise_floor_db: np.ndarray,
    threshold_db: float,
    min_bandwidth_bins: int,
    excluded_mask: np.ndarray | None = None,
) -> list[SpectralCluster]:
    """Находит связные группы бинов с SNR >= threshold_db, длиной >= min_bandwidth_bins.

    Частота кластера — центроид, взвешенный линейной мощностью бинов внутри
    группы (устойчивее к шуму периодограммы, чем один пиковый бин).

    excluded_mask (если задан) исключает отдельные бины из рассмотрения ещё
    до формирования кластеров — так кластер не может "перепрыгнуть" через
    исключённую зону и не усекается постфактум по центроиду.
    """
    snr_db = frame.power_db - noise_floor_db
    is_open = snr_db >= threshold_db
    if excluded_mask is not None:
        is_open = is_open & ~excluded_mask

    clusters: list[SpectralCluster] = []
    for start, end in _find_runs(is_open):
        if end - start < min_bandwidth_bins:
            continue

        segment_power_db = frame.power_db[start:end]
        segment_freqs_hz = frame.frequencies_hz[start:end]
        segment_snr_db = snr_db[start:end]

        peak_offset = int(np.argmax(segment_power_db))
        weights = np.power(10.0, segment_power_db.astype(np.float64) / 10.0)
        center_frequency_hz = float(np.average(segment_freqs_hz, weights=weights))

        clusters.append(
            SpectralCluster(
                center_frequency_hz=center_frequency_hz,
                peak_power_db=float(segment_power_db[peak_offset]),
                peak_snr_db=float(segment_snr_db[peak_offset]),
            )
        )

    return clusters


def _find_runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Возвращает [start, end) для каждой связной группы True в 1-D маске."""
    if not mask.any():
        return []
    padded = np.concatenate(([False], mask, [False]))
    diff = np.diff(padded.astype(np.int8))
    starts = np.flatnonzero(diff == 1)
    ends = np.flatnonzero(diff == -1)
    return list(zip(starts.tolist(), ends.tolist()))
