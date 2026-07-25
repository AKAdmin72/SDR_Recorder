import numpy as np

from sdr_monitor.dsp.windows import get_window


def test_rectangular_window_is_all_ones():
    window = get_window("rectangular", 16)
    np.testing.assert_array_equal(window, np.ones(16, dtype=np.float32))


def test_hann_window_has_expected_length_and_tapers_to_zero_at_edges():
    window = get_window("hann", 16)
    assert window.shape == (16,)
    assert window[0] == 0.0
    assert window.dtype == np.float32
