import pytest

from sdr_monitor.config.display_config import DisplayConfig

_VALID_KWARGS = dict(
    refresh_interval_s=0.5,
    queue_pump_interval_s=0.05,
    max_blocks_per_pump_tick=4,
    history_size=20,
    spectrum_y_margin_db=5.0,
)


def test_accepts_valid_values():
    config = DisplayConfig(**_VALID_KWARGS)
    assert config.history_size == 20


@pytest.mark.parametrize(
    "field,invalid_value",
    [
        ("refresh_interval_s", 0.0),
        ("refresh_interval_s", -1.0),
        ("queue_pump_interval_s", 0.0),
        ("max_blocks_per_pump_tick", 0),
        ("max_blocks_per_pump_tick", -1),
        ("history_size", 0),
        ("history_size", -1),
        ("spectrum_y_margin_db", -1.0),
    ],
)
def test_rejects_invalid_values(field, invalid_value):
    kwargs = dict(_VALID_KWARGS)
    kwargs[field] = invalid_value
    with pytest.raises(ValueError):
        DisplayConfig(**kwargs)
