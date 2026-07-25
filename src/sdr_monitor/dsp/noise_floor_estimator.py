"""Скользящая перцентильная оценка шумового пола по каждому бину."""

from __future__ import annotations

import logging

import numpy as np

from sdr_monitor.config.noise_floor_config import NoiseFloorConfig
from sdr_monitor.dsp.spectral_frame import SpectralFrame

_logger = logging.getLogger(__name__)


class NoiseFloorEstimator:
    """Отслеживает нижний перцентиль мощности в скользящем окне, по бину.

    Сигнал может только поднимать мощность бина выше истинного шума, никогда
    не понижать её ниже — поэтому нижний перцентиль устойчив к присутствию
    сигнала в окне, в отличие от экспоненциального сглаживания, которое
    затягивало бы шумовой пол вверх на время долгой передачи.

    Не зависит от FFTConfig/RadioConfig — только от контракта SpectralFrame.
    Размер окна в кадрах и период пересчёта в кадрах выводятся один раз из
    первого полученного кадра (длительность кадра постоянна на всём сеансе).
    """

    def __init__(self, config: NoiseFloorConfig) -> None:
        self._config = config

        self._bin_count: int | None = None
        self._window_frame_capacity: int | None = None
        self._recompute_interval_frames: int | None = None
        self._warmup_frames: int | None = None

        self._buffer: np.ndarray | None = None  # shape (capacity, bin_count), float32
        self._write_index = 0
        self._filled_frames = 0
        self._frames_since_recompute = 0

        self._noise_floor_db: np.ndarray | None = None

    @property
    def is_ready(self) -> bool:
        return self._noise_floor_db is not None

    def noise_floor_db(self) -> np.ndarray:
        """Текущая оценка шумового пола, shape (fft_size,), дБ."""
        if self._noise_floor_db is None:
            raise RuntimeError(
                "Noise floor estimate is not ready yet — insufficient accumulated history"
            )
        return self._noise_floor_db

    def update(self, frame: SpectralFrame) -> None:
        if self._bin_count is None:
            self._initialize_from_first_frame(frame)

        self._buffer[self._write_index] = frame.power_db
        self._write_index = (self._write_index + 1) % self._window_frame_capacity
        self._filled_frames = min(self._filled_frames + 1, self._window_frame_capacity)
        self._frames_since_recompute += 1

        if self._filled_frames < self._warmup_frames:
            return

        if (
            self._noise_floor_db is None
            or self._frames_since_recompute >= self._recompute_interval_frames
        ):
            self._recompute()

    def _initialize_from_first_frame(self, frame: SpectralFrame) -> None:
        bin_count = frame.power_db.shape[0]
        frame_duration_s = (frame.end_sample_index - frame.start_sample_index) / (
            frame.sample_rate_hz
        )

        self._bin_count = bin_count
        self._window_frame_capacity = max(1, round(self._config.window_seconds / frame_duration_s))
        self._recompute_interval_frames = max(
            1, round(self._config.update_interval_s / frame_duration_s)
        )
        self._warmup_frames = max(1, round(self._config.warmup_seconds / frame_duration_s))
        self._buffer = np.empty((self._window_frame_capacity, bin_count), dtype=np.float32)

        _logger.info(
            "NoiseFloorEstimator initialized: bin_count=%d, window=%d frames, "
            "recompute every %d frames, warmup %d frames",
            bin_count,
            self._window_frame_capacity,
            self._recompute_interval_frames,
            self._warmup_frames,
        )

    def _recompute(self) -> None:
        active_view = self._buffer[: self._filled_frames]
        self._noise_floor_db = np.percentile(
            active_view, self._config.percentile, axis=0
        ).astype(np.float32)
        self._frames_since_recompute = 0
