import pytest

from sdr_monitor.config.toml_writer import replace_array_of_tables, update_scalar

_SAMPLE = """\
[sdr]
type = "rtlsdr"

[radio.hackrf]
# Комментарий про частоту HackRF.
center_frequency_hz = 123_600_000
amp_enable = false

[radio.rtlsdr]
# Комментарий про частоту RTL-SDR.
center_frequency_hz = 446_600_000
gain_db = 40.2
agc_enabled = false
"""


def test_replaces_int_and_preserves_rest_of_file():
    result = update_scalar(_SAMPLE, "radio.rtlsdr", "center_frequency_hz", 155_400_000)

    assert "center_frequency_hz = 155_400_000" in result
    # Комментарии и соседние секции не тронуты.
    assert "# Комментарий про частоту RTL-SDR." in result
    assert "# Комментарий про частоту HackRF." in result
    assert "center_frequency_hz = 123_600_000" in result  # секция hackrf не тронута


def test_does_not_touch_same_key_in_other_section():
    result = update_scalar(_SAMPLE, "radio.hackrf", "center_frequency_hz", 100_000_000)

    assert "center_frequency_hz = 100_000_000" in result
    assert "center_frequency_hz = 446_600_000" in result  # rtlsdr не тронут


def test_replaces_bool():
    result = update_scalar(_SAMPLE, "radio.rtlsdr", "agc_enabled", True)
    assert "agc_enabled = true" in result


def test_replaces_float():
    result = update_scalar(_SAMPLE, "radio.rtlsdr", "gain_db", 33.8)
    assert "gain_db = 33.8" in result


def test_replaces_string_with_quotes():
    result = update_scalar(_SAMPLE, "sdr", "type", "hackrf")
    assert 'type = "hackrf"' in result


def test_small_int_not_grouped():
    result = update_scalar(_SAMPLE, "radio.rtlsdr", "center_frequency_hz", 8000)
    assert "center_frequency_hz = 8000" in result


def test_line_count_unchanged():
    result = update_scalar(_SAMPLE, "radio.rtlsdr", "gain_db", 10.0)
    assert result.count("\n") == _SAMPLE.count("\n")


def test_unknown_section_raises():
    with pytest.raises(ValueError, match=r"\[radio\.nonexistent\]"):
        update_scalar(_SAMPLE, "radio.nonexistent", "gain_db", 1.0)


def test_unknown_key_raises():
    with pytest.raises(ValueError, match="not_a_real_field"):
        update_scalar(_SAMPLE, "radio.rtlsdr", "not_a_real_field", 1.0)


_SAMPLE_WITH_BLACKLIST = """\
[detection]
open_threshold_db = 10.0
close_threshold_db = 6.0

# Диапазоны частот, полностью исключённые из детекции.
# 125.9-126.25 МГц — известная гребёнка паразитных отражений.
[[detection.blacklisted_ranges]]
start_hz = 125_900_000
end_hz = 126_250_000

[display]
refresh_interval_s = 0.5
"""


def test_replace_array_of_tables_changes_existing_entry():
    result = replace_array_of_tables(
        _SAMPLE_WITH_BLACKLIST,
        "detection.blacklisted_ranges",
        [{"start_hz": 100_000_000, "end_hz": 101_000_000}],
    )

    assert "start_hz = 100_000_000" in result
    assert "end_hz = 101_000_000" in result
    assert "125_900_000" not in result
    # Комментарии и соседние секции не тронуты.
    assert "# Диапазоны частот, полностью исключённые из детекции." in result
    assert "open_threshold_db = 10.0" in result
    assert "refresh_interval_s = 0.5" in result


def test_replace_array_of_tables_adds_second_entry():
    result = replace_array_of_tables(
        _SAMPLE_WITH_BLACKLIST,
        "detection.blacklisted_ranges",
        [
            {"start_hz": 125_900_000, "end_hz": 126_250_000},
            {"start_hz": 200_000_000, "end_hz": 201_000_000},
        ],
    )

    assert result.count("[[detection.blacklisted_ranges]]") == 2
    assert "start_hz = 200_000_000" in result
    assert "end_hz = 201_000_000" in result
    assert "refresh_interval_s = 0.5" in result


def test_replace_array_of_tables_removes_all_entries():
    result = replace_array_of_tables(_SAMPLE_WITH_BLACKLIST, "detection.blacklisted_ranges", [])

    assert "[[detection.blacklisted_ranges]]" not in result
    assert "start_hz" not in result
    assert "open_threshold_db = 10.0" in result
    assert "refresh_interval_s = 0.5" in result


def test_replace_array_of_tables_inserts_when_none_exist():
    sample_without_blacklist = """\
[detection]
open_threshold_db = 10.0

[display]
refresh_interval_s = 0.5
"""
    result = replace_array_of_tables(
        sample_without_blacklist,
        "detection.blacklisted_ranges",
        [{"start_hz": 1_000_000, "end_hz": 2_000_000}],
    )

    assert "[[detection.blacklisted_ranges]]" in result
    assert "start_hz = 1_000_000" in result
    # вставлено между [detection] и [display], а не в конец файла
    assert result.index("[[detection.blacklisted_ranges]]") < result.index("[display]")


def test_replace_array_of_tables_result_is_valid_toml():
    import tomllib

    result = replace_array_of_tables(
        _SAMPLE_WITH_BLACKLIST,
        "detection.blacklisted_ranges",
        [
            {"start_hz": 1_000_000, "end_hz": 2_000_000},
            {"start_hz": 3_000_000, "end_hz": 4_000_000},
        ],
    )
    parsed = tomllib.loads(result)
    assert parsed["detection"]["blacklisted_ranges"] == [
        {"start_hz": 1_000_000, "end_hz": 2_000_000},
        {"start_hz": 3_000_000, "end_hz": 4_000_000},
    ]
