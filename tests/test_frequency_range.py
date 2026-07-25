import pytest

from sdr_monitor.config.frequency_range import FrequencyRange


def test_accepts_valid_range():
    frequency_range = FrequencyRange(start_hz=125_900_000.0, end_hz=126_250_000.0)
    assert frequency_range.start_hz == 125_900_000.0


@pytest.mark.parametrize("end_hz", [125_900_000.0, 125_000_000.0])
def test_rejects_end_not_after_start(end_hz):
    with pytest.raises(ValueError):
        FrequencyRange(start_hz=125_900_000.0, end_hz=end_hz)
