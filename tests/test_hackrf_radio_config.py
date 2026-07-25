import pytest

from sdr_monitor.config.hackrf_radio_config import HackRFRadioConfig

_VALID_KWARGS = dict(
    center_frequency_hz=128_000_000,
    sample_rate_hz=2_000_000,
    lna_gain_db=24,
    vga_gain_db=20,
    amp_enable=False,
    settle_time_s=5.0,
)


def test_accepts_valid_values():
    config = HackRFRadioConfig(**_VALID_KWARGS)
    assert config.center_frequency_hz == 128_000_000
    assert config.sample_rate_hz == 2_000_000


@pytest.mark.parametrize(
    "field,invalid_value",
    [
        ("center_frequency_hz", 100),
        ("center_frequency_hz", 10_000_000_000),
        ("sample_rate_hz", 1_000_000),
        ("sample_rate_hz", 25_000_000),
        ("lna_gain_db", 5),
        ("lna_gain_db", 48),
        ("vga_gain_db", 3),
        ("vga_gain_db", 64),
        ("settle_time_s", -1.0),
    ],
)
def test_rejects_invalid_values(field, invalid_value):
    kwargs = dict(_VALID_KWARGS)
    kwargs[field] = invalid_value
    with pytest.raises(ValueError):
        HackRFRadioConfig(**kwargs)
