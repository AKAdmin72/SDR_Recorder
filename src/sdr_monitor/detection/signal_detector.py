"""Стейт-машина детекции: гистерезис во времени поверх кластеров по частоте."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

from sdr_monitor.config.detection_config import DetectionConfig
from sdr_monitor.config.frequency_range import FrequencyRange
from sdr_monitor.detection.active_signal import ActiveSignal
from sdr_monitor.detection.detected_signal import DetectedSignal
from sdr_monitor.detection.spectral_cluster import SpectralCluster, find_clusters
from sdr_monitor.dsp.spectral_frame import SpectralFrame


class _TrackState(enum.Enum):
    PROVISIONAL = enum.auto()
    CONFIRMED = enum.auto()


@dataclass(slots=True)
class _Track:
    track_id: int
    center_frequency_hz: float
    state: _TrackState
    hit_streak: int
    trigger_sample_index: int
    last_hit_end_sample_index: int
    peak_power_db: float
    peak_snr_db: float
    last_power_db: float
    last_snr_db: float
    miss_streak: int = 0


class SignalDetector:
    """Обнаруживает передачи по потоку SpectralFrame + шумовому полу по бинам.

    Двухпороговый (по образцу Canny) гистерезис во времени: непойманный
    кластер выше open_threshold_db порождает PROVISIONAL-трек; после
    open_confirm_frames подряд успешных попаданий он становится CONFIRMED.
    CONFIRMED-трек удерживается более мягким close_threshold_db (переживает
    естественные провалы огибающей AM-голоса), пока не пропустит
    close_confirm_frames кадров подряд — тогда передача завершена и
    репортится как DetectedSignal.

    Сопоставление трек<->кластер — жадное по ближайшей частоте, не
    оптимальное (без венгерского алгоритма); этого достаточно при малом
    числе одновременно активных каналов в 2 МГц авиаполосы.
    """

    def __init__(self, config: DetectionConfig) -> None:
        self._config = config
        self._tracks: list[_Track] = []
        self._stream_start_utc: datetime | None = None
        self._sample_rate_hz: int | None = None
        self._blacklist_mask: np.ndarray | None = None
        self._next_track_id = 0

    def update(self, frame: SpectralFrame, noise_floor_db: np.ndarray) -> list[DetectedSignal]:
        """Обрабатывает один кадр, возвращает передачи, завершившиеся на этом шаге."""
        if self._stream_start_utc is None:
            self._stream_start_utc = frame.stream_start_utc
            self._sample_rate_hz = frame.sample_rate_hz
        if self._blacklist_mask is None:
            self._blacklist_mask = _compute_blacklist_mask(
                frame.frequencies_hz, self._config.blacklisted_ranges
            )

        open_clusters = find_clusters(
            frame,
            noise_floor_db,
            self._config.open_threshold_db,
            self._config.min_bandwidth_bins,
            self._blacklist_mask,
        )
        close_clusters = find_clusters(
            frame,
            noise_floor_db,
            self._config.close_threshold_db,
            self._config.min_bandwidth_bins,
            self._blacklist_mask,
        )

        finalized: list[DetectedSignal] = []
        surviving_tracks: list[_Track] = []

        for track in self._tracks:
            if track.state is _TrackState.PROVISIONAL:
                match = _pop_nearest(
                    open_clusters,
                    track.center_frequency_hz,
                    self._config.frequency_match_tolerance_hz,
                )
                if match is None:
                    continue  # одиночный пропуск -> кандидат отбрасывается целиком
                self._register_hit(track, frame, match)
                track.hit_streak += 1
                if track.hit_streak >= self._config.open_confirm_frames:
                    track.state = _TrackState.CONFIRMED
                surviving_tracks.append(track)
            else:
                match = _pop_nearest(
                    close_clusters,
                    track.center_frequency_hz,
                    self._config.frequency_match_tolerance_hz,
                )
                if match is not None:
                    self._register_hit(track, frame, match)
                    track.miss_streak = 0
                    surviving_tracks.append(track)
                else:
                    track.miss_streak += 1
                    if track.miss_streak >= self._config.close_confirm_frames:
                        finalized.append(self._finalize(track))
                    else:
                        surviving_tracks.append(track)

        for cluster in open_clusters:  # оставшиеся непойманные -> новые кандидаты
            surviving_tracks.append(self._spawn_track(frame, cluster))

        self._tracks = surviving_tracks
        return finalized

    def active_signals(self) -> list[ActiveSignal]:
        """Текущее состояние подтверждённых, но ещё не закрытых треков.

        Read-only: не завершает и не изменяет треки, можно вызывать после
        каждого update() для живого отображения.
        """
        return [
            ActiveSignal(
                track_id=track.track_id,
                center_frequency_hz=track.center_frequency_hz,
                current_level_db=track.last_power_db,
                current_snr_db=track.last_snr_db,
                peak_level_db=track.peak_power_db,
                peak_snr_db=track.peak_snr_db,
                start_time_utc=self._stream_start_utc
                + timedelta(seconds=track.trigger_sample_index / self._sample_rate_hz),
                elapsed_s=(track.last_hit_end_sample_index - track.trigger_sample_index)
                / self._sample_rate_hz,
            )
            for track in self._tracks
            if track.state is _TrackState.CONFIRMED
        ]

    def flush(self) -> list[DetectedSignal]:
        """Принудительно завершает все CONFIRMED-треки (например, при остановке приёма).

        PROVISIONAL-треки отбрасываются без репорта — они и не были
        подтверждённой передачей.
        """
        finalized = [
            self._finalize(track)
            for track in self._tracks
            if track.state is _TrackState.CONFIRMED
        ]
        self._tracks = []
        return finalized

    def _register_hit(
        self, track: _Track, frame: SpectralFrame, cluster: SpectralCluster
    ) -> None:
        track.center_frequency_hz = cluster.center_frequency_hz
        track.last_hit_end_sample_index = frame.end_sample_index
        track.last_power_db = cluster.peak_power_db
        track.last_snr_db = cluster.peak_snr_db
        if cluster.peak_power_db > track.peak_power_db:
            track.peak_power_db = cluster.peak_power_db
            track.peak_snr_db = cluster.peak_snr_db

    def _spawn_track(self, frame: SpectralFrame, cluster: SpectralCluster) -> _Track:
        track = _Track(
            track_id=self._next_track_id,
            center_frequency_hz=cluster.center_frequency_hz,
            state=_TrackState.PROVISIONAL,
            hit_streak=1,
            trigger_sample_index=frame.start_sample_index,
            last_hit_end_sample_index=frame.end_sample_index,
            peak_power_db=cluster.peak_power_db,
            peak_snr_db=cluster.peak_snr_db,
            last_power_db=cluster.peak_power_db,
            last_snr_db=cluster.peak_snr_db,
        )
        if track.hit_streak >= self._config.open_confirm_frames:
            track.state = _TrackState.CONFIRMED
        self._next_track_id += 1
        return track

    def _finalize(self, track: _Track) -> DetectedSignal:
        start_time = self._stream_start_utc + timedelta(
            seconds=track.trigger_sample_index / self._sample_rate_hz
        )
        end_time = self._stream_start_utc + timedelta(
            seconds=track.last_hit_end_sample_index / self._sample_rate_hz
        )
        return DetectedSignal(
            track_id=track.track_id,
            center_frequency_hz=track.center_frequency_hz,
            peak_level_db=track.peak_power_db,
            peak_snr_db=track.peak_snr_db,
            start_time_utc=start_time,
            end_time_utc=end_time,
            duration_s=(end_time - start_time).total_seconds(),
        )


def _compute_blacklist_mask(
    frequencies_hz: np.ndarray, blacklisted_ranges: tuple[FrequencyRange, ...]
) -> np.ndarray:
    """True для бинов, попадающих в любой из blacklisted_ranges — исключены из детекции."""
    mask = np.zeros(frequencies_hz.shape[0], dtype=bool)
    for frequency_range in blacklisted_ranges:
        mask |= (frequencies_hz >= frequency_range.start_hz) & (
            frequencies_hz < frequency_range.end_hz
        )
    return mask


def _pop_nearest(
    clusters: list[SpectralCluster], target_frequency_hz: float, tolerance_hz: float
) -> SpectralCluster | None:
    """Находит и удаляет из `clusters` ближайший к target_frequency_hz в пределах допуска."""
    best_index: int | None = None
    best_distance = tolerance_hz
    for index, cluster in enumerate(clusters):
        distance = abs(cluster.center_frequency_hz - target_frequency_hz)
        if distance <= best_distance:
            best_distance = distance
            best_index = index
    if best_index is None:
        return None
    return clusters.pop(best_index)
