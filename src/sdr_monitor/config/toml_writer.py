"""Точечная (без пересборки файла) правка скалярных значений в TOML-тексте.

Нужно GUI-редактору конфига: config/app_config.toml насыщен пояснительными
комментариями почти на каждое поле — обычный цикл "распарсить в dict ->
сериализовать обратно" их уничтожит. update_scalar() меняет только значение
после `key =` на нужной строке нужной секции, всё остальное (комментарии,
пустые строки, другие секции) остаётся байт-в-байт как было.
"""

from __future__ import annotations

import re

_KEY_LINE_RE_TEMPLATE = r"^(?P<prefix>\s*{key}\s*=\s*)(?P<rest>.*)$"


def update_scalar(text: str, section: str, key: str, value: bool | int | float | str) -> str:
    """Заменяет значение key внутри [section] (например "radio.rtlsdr").

    Ищет секцию по точному совпадению строки `[section]`, затем строку
    `key = ...` до начала следующей секции (`[...]`). Сохраняет отступ и
    построчный хвостовой комментарий (`# ...`), если он был. Бросает
    ValueError, если секция или ключ не найдены — это обычно означает
    рассинхронизацию схемы редактора с реальным конфигом.
    """
    section_header = f"[{section}]"
    lines = text.split("\n")

    section_start = next(
        (i for i, line in enumerate(lines) if line.strip() == section_header), None
    )
    if section_start is None:
        raise ValueError(f"Section [{section}] not found in config")

    section_end = _find_section_end(lines, section_start)

    key_pattern = re.compile(_KEY_LINE_RE_TEMPLATE.format(key=re.escape(key)))
    for i in range(section_start + 1, section_end):
        match = key_pattern.match(lines[i])
        if match is None:
            continue
        rest = match.group("rest")
        comment_idx = rest.find("#")
        trailing_comment = rest[comment_idx:] if comment_idx != -1 else ""
        new_line = f"{match.group('prefix')}{_format_value(value)}"
        if trailing_comment:
            new_line += f"  {trailing_comment}"
        lines[i] = new_line
        return "\n".join(lines)

    raise ValueError(f"Field {key!r} not found in section [{section}]")


def replace_array_of_tables(
    text: str, dotted_path: str, entries: list[dict[str, bool | int | float | str]]
) -> str:
    """Полностью перегенерирует все блоки `[[dotted_path]]` из entries.

    В отличие от update_scalar(), тут нет разумного "того же значения на той
    же строке" — записей может стать больше или меньше, поэтому весь диапазон
    существующих блоков `[[dotted_path]]` (от первого до конца последнего)
    заменяется целиком. Комментарии ДО первого блока (обычно поясняющие сам
    список) сохраняются на месте; если блоков раньше не было — новые
    вставляются сразу после родительской секции `[parent]`
    (`dotted_path.rsplit(".", 1)[0]`).
    """
    header = f"[[{dotted_path}]]"
    parent_section = dotted_path.rsplit(".", 1)[0]
    lines = text.split("\n")

    block_starts = [i for i, line in enumerate(lines) if line.strip() == header]

    if block_starts:
        region_start = block_starts[0]
        region_end = _find_section_end(lines, block_starts[-1])
    else:
        parent_header = f"[{parent_section}]"
        parent_start = next(
            (i for i, line in enumerate(lines) if line.strip() == parent_header), None
        )
        if parent_start is None:
            raise ValueError(f"Section [{parent_section}] not found in config")
        region_end = _find_section_end(lines, parent_start)
        region_start = region_end

    new_lines: list[str] = []
    for i, entry in enumerate(entries):
        if i > 0:
            new_lines.append("")
        new_lines.append(header)
        new_lines.extend(f"{key} = {_format_value(value)}" for key, value in entry.items())
    if entries:
        new_lines.append("")

    return "\n".join(lines[:region_start] + new_lines + lines[region_end:])


def _find_section_end(lines: list[str], section_start: int) -> int:
    """Индекс строки, где начинается следующая секция после lines[section_start], либо len(lines)."""
    for i in range(section_start + 1, len(lines)):
        if lines[i].strip().startswith("["):
            return i
    return len(lines)


def _format_value(value: bool | int | float | str) -> str:
    # bool до int — в Python bool является подклассом int, isinstance(True, int) тоже True.
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, float):
        return repr(value)  # repr() всегда даёт "N.0" для целых float — валидный TOML
    if isinstance(value, int):
        return _group_thousands(value)
    raise TypeError(f"Unsupported value type for TOML: {type(value)!r}")


def _group_thousands(value: int) -> str:
    # Косметика под стиль файла (2_000_000, 126_600_000) — не требование TOML.
    text = str(abs(value))
    if len(text) <= 4:
        return str(value)
    groups = []
    while len(text) > 3:
        groups.insert(0, text[-3:])
        text = text[:-3]
    groups.insert(0, text)
    sign = "-" if value < 0 else ""
    return sign + "_".join(groups)
