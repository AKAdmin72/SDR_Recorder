"""Итоговое событие детектора — одна завершённая передача."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class DetectedSignal:
    """Полностью определившаяся (открытая и закрытая) передача.

    `peak_level_db`/`peak_snr_db` — максимум за всё время передачи, не
    значение в какой-то конкретный момент. `start_time_utc`/`end_time_utc`
    не включают задержку гистерезиса на подтверждение открытия/закрытия —
    это моменты первого и последнего реального обнаружения кластера.

    `track_id` — тот же идентификатор, что был у трека в ActiveSignal, пока
    он был открыт (см. ActiveSignal.track_id).
    """

    track_id: int
    center_frequency_hz: float
    peak_level_db: float
    peak_snr_db: float
    start_time_utc: datetime
    end_time_utc: datetime
    duration_s: float
