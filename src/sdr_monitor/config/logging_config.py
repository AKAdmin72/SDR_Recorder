"""Параметры логирования."""

from __future__ import annotations

from dataclasses import dataclass

_VALID_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


@dataclass(frozen=True, slots=True)
class LoggingConfig:
    level: str

    def __post_init__(self) -> None:
        if self.level not in _VALID_LEVELS:
            raise ValueError(f"level={self.level!r} is not one of {sorted(_VALID_LEVELS)}")
