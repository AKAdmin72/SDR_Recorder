"""Единица передачи данных между приёмным конвейером и потребителями."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np


@dataclass(frozen=True, slots=True)
class IQBlock:
    """Один блок IQ-отсчётов, полученный из RX-callback HackRF.

    Время привязано не к wall-clock моменту получения блока (подвержен
    джиттеру планировщика ОС), а к номеру отсчёта в непрерывном потоке —
    так время любого отсчёта восстанавливается детерминированно из частоты
    дискретизации.
    """

    samples: np.ndarray  # dtype complex64, shape (n,)
    sample_index: int  # номер первого отсчёта блока с начала потока
    sample_rate_hz: int
    stream_start_utc: datetime  # момент времени, соответствующий sample_index=0

    @property
    def start_time_utc(self) -> datetime:
        return self.stream_start_utc + timedelta(
            seconds=self.sample_index / self.sample_rate_hz
        )

    @property
    def duration_s(self) -> float:
        return self.samples.shape[0] / self.sample_rate_hz
