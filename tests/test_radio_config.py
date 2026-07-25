import pytest

from sdr_monitor.config.radio_config import RadioConfig

_VALID_KWARGS = dict(
    center_frequency_hz=128_000_000,
    sample_rate_hz=2_000_000,
    settle_time_s=5.0,
)


def test_accepts_valid_values():
    config = RadioConfig(**_VALID_KWARGS)
    assert config.center_frequency_hz == 128_000_000
    assert config.sample_rate_hz == 2_000_000


def test_rejects_negative_settle_time():
    kwargs = dict(_VALID_KWARGS)
    kwargs["settle_time_s"] = -1.0
    with pytest.raises(ValueError):
        RadioConfig(**kwargs)
