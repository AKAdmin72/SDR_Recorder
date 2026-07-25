from datetime import datetime, timezone

import numpy as np
import pytest

from sdr_monitor.dsp.spectral_frame import SpectralFrame


def test_start_and_end_time_derived_from_sample_index():
    stream_start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    frame = SpectralFrame(
        frequencies_hz=np.array([1.0, 2.0]),
        power_db=np.array([-90.0, -80.0], dtype=np.float32),
        start_sample_index=2_000_000,
        end_sample_index=2_002_048,
        sample_rate_hz=2_000_000,
        stream_start_utc=stream_start,
    )

    assert (frame.start_time_utc - stream_start).total_seconds() == 1.0
    assert (frame.end_time_utc - stream_start).total_seconds() == pytest.approx(1.001024)
