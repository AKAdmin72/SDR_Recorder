import pytest

from sdr_monitor.config.detection_config import DetectionConfig
from sdr_monitor.config.frequency_range import FrequencyRange

_VALID_KWARGS = dict(
    open_threshold_db=10.0,
    close_threshold_db=6.0,
    min_bandwidth_bins=3,
    open_confirm_frames=3,
    close_confirm_frames=15,
    frequency_match_tolerance_hz=3000.0,
)


def test_accepts_valid_values():
    config = DetectionConfig(**_VALID_KWARGS)
    assert config.open_threshold_db == 10.0


def test_blacklisted_ranges_defaults_to_empty():
    config = DetectionConfig(**_VALID_KWARGS)
    assert config.blacklisted_ranges == ()


def test_accepts_blacklisted_ranges():
    ranges = (FrequencyRange(start_hz=125_900_000.0, end_hz=126_250_000.0),)
    config = DetectionConfig(blacklisted_ranges=ranges, **_VALID_KWARGS)
    assert config.blacklisted_ranges == ranges


@pytest.mark.parametrize(
    "field,invalid_value",
    [
        ("close_threshold_db", 10.0),  # равен open -> нет гистерезиса
        ("close_threshold_db", 12.0),  # больше open
        ("min_bandwidth_bins", 0),
        ("open_confirm_frames", 0),
        ("close_confirm_frames", 0),
        ("frequency_match_tolerance_hz", 0.0),
        ("frequency_match_tolerance_hz", -100.0),
    ],
)
def test_rejects_invalid_values(field, invalid_value):
    kwargs = dict(_VALID_KWARGS)
    kwargs[field] = invalid_value
    with pytest.raises(ValueError):
        DetectionConfig(**kwargs)
