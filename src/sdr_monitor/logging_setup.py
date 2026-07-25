"""Единая точка настройки логирования приложения."""

from __future__ import annotations

import logging
import sys

_LOG_FORMAT = "%(asctime)s.%(msecs)03d [%(levelname)-7s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(level: str) -> None:
    """Настраивает корневой логгер приложения. Вызывается один раз при старте."""
    # Консоль Windows по умолчанию открывает stdout в codepage (напр. cp1252),
    # который не может закодировать кириллицу из наших лог-сообщений.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    logging.basicConfig(
        level=level,
        format=_LOG_FORMAT,
        datefmt=_DATE_FORMAT,
        stream=sys.stdout,
    )
