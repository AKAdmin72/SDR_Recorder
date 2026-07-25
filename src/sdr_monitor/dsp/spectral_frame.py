"""Результат усреднения группы FFT-окон — один спектральный кадр."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np


@dataclass(frozen=True, slots=True)
class SpectralFrame:
    """Усреднённый спектр за интервал [start_sample_index, end_sample_index).

    `frequencies_hz` — абсолютные частоты бинов (уже со сдвигом на центральную
    частоту, по возрастанию). `power_db` — мощность бина в относительных дБ
    (не калиброванных дБм), той же длины и порядка, что и `frequencies_hz`.
    Время, как и в IQBlock, выводится из номера отсчёта, а не wall-clock.
    """

    frequencies_hz: np.ndarray
    power_db: np.ndarray
    start_sample_index: int
    end_sample_index: int
    sample_rate_hz: int
    stream_start_utc: datetime

    @property
    def start_time_utc(self) -> datetime:
        return self.stream_start_utc + timedelta(
            seconds=self.start_sample_index / self.sample_rate_hz
        )

    @property
    def end_time_utc(self) -> datetime:
        return self.stream_start_utc + timedelta(
            seconds=self.end_sample_index / self.sample_rate_hz
        )
