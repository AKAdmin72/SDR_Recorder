import pytest

from sdr_monitor.config.rtlsdr_radio_config import RtlSdrRadioConfig

_VALID_KWARGS = dict(
    center_frequency_hz=126_900_000,
    sample_rate_hz=2_048_000,
    gain_db=40.2,
    agc_enabled=False,
    freq_correction_ppm=0,
    settle_time_s=2.0,
    read_async_buffer_count=15,
    read_async_buffer_length=262_144,
)


def test_accepts_valid_values():
    config = RtlSdrRadioConfig(**_VALID_KWARGS)
    assert config.center_frequency_hz == 126_900_000
    assert config.sample_rate_hz == 2_048_000
    assert config.gain_db == 40.2


def test_accepts_agc_enabled():
    kwargs = dict(_VALID_KWARGS)
    kwargs["agc_enabled"] = True
    config = RtlSdrRadioConfig(**kwargs)
    assert config.agc_enabled is True


@pytest.mark.parametrize(
    "field,invalid_value",
    [
        ("center_frequency_hz", 1_000_000),
        ("center_frequency_hz", 2_000_000_000),
        ("sample_rate_hz", 100_000),
        ("sample_rate_hz", 5_000_000),
        ("gain_db", -1.0),
        ("gain_db", 100.0),
        ("settle_time_s", -1.0),
        ("read_async_buffer_count", 0),
        ("read_async_buffer_length", 0),
        ("read_async_buffer_length", 1000),  # не кратно 512
    ],
)
def test_rejects_invalid_values(field, invalid_value):
    kwargs = dict(_VALID_KWARGS)
    kwargs[field] = invalid_value
    with pytest.raises(ValueError):
        RtlSdrRadioConfig(**kwargs)
