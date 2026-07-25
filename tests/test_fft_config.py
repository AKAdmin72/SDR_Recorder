import pytest

from sdr_monitor.config.fft_config import FFTConfig

_VALID_KWARGS = dict(fft_size=2048, window_type="hann", averaging_count=8, dc_notch_bins=2)


def test_accepts_valid_values():
    config = FFTConfig(**_VALID_KWARGS)
    assert config.fft_size == 2048


@pytest.mark.parametrize(
    "field,invalid_value",
    [
        ("fft_size", 1000),  # не степень двойки
        ("fft_size", 32),  # меньше минимума
        ("window_type", "kaiser"),  # не в поддерживаемом наборе
        ("averaging_count", 0),
        ("dc_notch_bins", -1),
        ("dc_notch_bins", 1024),  # >= fft_size // 2
    ],
)
def test_rejects_invalid_values(field, invalid_value):
    kwargs = dict(_VALID_KWARGS)
    kwargs[field] = invalid_value
    with pytest.raises(ValueError):
        FFTConfig(**kwargs)
