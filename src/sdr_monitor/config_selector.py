"""Выбор пути к TOML-конфигу при запуске без явного --config.

Каталог config/ может содержать несколько именованных профилей (разные SDR/
частоты/режимы) — без этого модуля пришлось бы помнить и печатать точный
путь к нужному файлу при каждом запуске.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

_DEFAULT_CONFIG_NAME = "app_config.toml"


def select_config_path(
    config_dir: Path,
    explicit_path: Path | None,
    input_func: Callable[[str], str] = input,
) -> Path:
    """Возвращает путь к конфигу для запуска.

    explicit_path (значение --config) имеет приоритет и возвращается как
    есть без обращения к config_dir. Иначе сканируется config_dir на *.toml:
    ни одного — ошибка, один — возвращается сразу, несколько — печатается
    текстовое меню (пропускается, если stdin не интерактивен — тогда молча
    берётся умолчание).
    """
    if explicit_path is not None:
        return explicit_path

    candidates = sorted(config_dir.glob("*.toml"))
    if not candidates:
        raise FileNotFoundError(f"No .toml config found in {config_dir}")
    if len(candidates) == 1:
        return candidates[0]

    default_index = next(
        (i for i, path in enumerate(candidates) if path.name == _DEFAULT_CONFIG_NAME), 0
    )

    if not sys.stdin.isatty():
        chosen = candidates[default_index]
        print(f"No interactive terminal — using default config: {chosen.name}")
        return chosen

    print(f"Available configs in {config_dir}:")
    for i, path in enumerate(candidates):
        marker = " (default)" if i == default_index else ""
        print(f"  {i + 1}) {path.name}{marker}")

    while True:
        raw = input_func(f"Choose a number [{default_index + 1}]: ").strip()
        if raw == "":
            return candidates[default_index]
        if raw.isdigit() and 1 <= int(raw) <= len(candidates):
            return candidates[int(raw) - 1]
        print(f"Invalid input {raw!r}, try again.")
