"""Текущее состояние ещё не завершившейся (CONFIRMED) передачи."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ActiveSignal:
    """Снимок состояния подтверждённого, но ещё не закрытого трека.

    `current_*` — значения последнего совпавшего кластера (что происходит
    прямо сейчас), `peak_*` — максимум за всё время трека с момента открытия.

    `track_id` — стабильный идентификатор трека, присваивается один раз при
    подтверждении и не меняется до закрытия (см. DetectedSignal.track_id) —
    позволяет внешним потребителям (например, записи WAV) сопоставлять
    события открытия/закрытия одной и той же передачи без повторной
    реализации логики сопоставления по частоте, уже имеющейся в SignalDetector.
    """

    track_id: int
    center_frequency_hz: float
    current_level_db: float
    current_snr_db: float
    peak_level_db: float
    peak_snr_db: float
    start_time_utc: datetime
    elapsed_s: float
