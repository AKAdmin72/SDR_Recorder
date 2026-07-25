import pytest

from sdr_monitor.config.logging_config import LoggingConfig


def test_accepts_valid_level():
    assert LoggingConfig(level="INFO").level == "INFO"


def test_rejects_invalid_level():
    with pytest.raises(ValueError):
        LoggingConfig(level="VERBOSE")
