import numpy as np

from sdr_monitor.audio.am_demodulator import AmDemodulator


def test_process_matches_abs():
    demod = AmDemodulator()
    samples = np.array([3 + 4j, -1 + 0j, 0 - 2j], dtype=np.complex64)

    result = demod.process(samples)

    np.testing.assert_allclose(result, [5.0, 1.0, 2.0], atol=1e-6)
    assert result.dtype == np.float32


def test_empty_input_returns_empty_output():
    demod = AmDemodulator()

    result = demod.process(np.empty(0, dtype=np.complex64))

    assert result.size == 0
    assert result.dtype == np.float32
