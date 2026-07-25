import pytest

from sdr_monitor.config.acquisition_config import AcquisitionConfig


def test_accepts_valid_values():
    config = AcquisitionConfig(queue_max_blocks=64, stats_log_interval_s=5.0)
    assert config.queue_max_blocks == 64


@pytest.mark.parametrize(
    "field,invalid_value",
    [
        ("queue_max_blocks", 0),
        ("queue_max_blocks", -1),
        ("stats_log_interval_s", 0.0),
        ("stats_log_interval_s", -1.0),
    ],
)
def test_rejects_invalid_values(field, invalid_value):
    kwargs = dict(queue_max_blocks=64, stats_log_interval_s=5.0)
    kwargs[field] = invalid_value
    with pytest.raises(ValueError):
        AcquisitionConfig(**kwargs)
