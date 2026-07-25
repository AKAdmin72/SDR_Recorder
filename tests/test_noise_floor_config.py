import pytest

from sdr_monitor.config.noise_floor_config import NoiseFloorConfig

_VALID_KWARGS = dict(
    window_seconds=10.0, update_interval_s=1.0, percentile=10.0, warmup_seconds=3.0
)


def test_accepts_valid_values():
    config = NoiseFloorConfig(**_VALID_KWARGS)
    assert config.window_seconds == 10.0


@pytest.mark.parametrize(
    "field,invalid_value",
    [
        ("window_seconds", 0.0),
        ("window_seconds", -1.0),
        ("update_interval_s", 0.0),
        ("percentile", 0.0),
        ("percentile", 100.0),
        ("percentile", -5.0),
        ("warmup_seconds", -1.0),
        ("warmup_seconds", 20.0),  # больше window_seconds
    ],
)
def test_rejects_invalid_values(field, invalid_value):
    kwargs = dict(_VALID_KWARGS)
    kwargs[field] = invalid_value
    with pytest.raises(ValueError):
        NoiseFloorConfig(**kwargs)
