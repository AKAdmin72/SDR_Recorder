import numpy as np
import pytest

from sdr_monitor.dsp.decimator import Decimator


def _make_tone(freq_hz: float, sample_rate_hz: float, n_samples: int) -> np.ndarray:
    t = np.arange(n_samples) / sample_rate_hz
    return np.exp(2j * np.pi * freq_hz * t).astype(np.complex64)


def test_output_length_scales_with_factor():
    dec = Decimator(factor=5, cutoff_hz=1000.0, input_sample_rate_hz=10000.0, num_taps=63)
    out = dec.process(_make_tone(0.0, 10000.0, 1000))
    assert out.shape[0] == 200


def test_passband_tone_survives_with_expected_amplitude():
    fs = 10000.0
    dec = Decimator(factor=5, cutoff_hz=1000.0, input_sample_rate_hz=fs, num_taps=127)
    out = dec.process(_make_tone(200.0, fs, 4000))
    steady = out[50:]
    assert np.mean(np.abs(steady)) == pytest.approx(1.0, rel=0.1)


def test_stopband_tone_is_attenuated():
    fs = 10000.0
    dec = Decimator(factor=5, cutoff_hz=1000.0, input_sample_rate_hz=fs, num_taps=127)
    out = dec.process(_make_tone(3000.0, fs, 4000))
    steady = out[50:]
    assert np.mean(np.abs(steady)) < 0.1


def test_split_calls_match_single_call():
    fs = 10000.0
    x = _make_tone(200.0, fs, 1000)

    dec_single = Decimator(factor=5, cutoff_hz=1000.0, input_sample_rate_hz=fs, num_taps=63)
    out_single = dec_single.process(x)

    dec_split = Decimator(factor=5, cutoff_hz=1000.0, input_sample_rate_hz=fs, num_taps=63)
    out_a = dec_split.process(x[:333])
    out_b = dec_split.process(x[333:777])
    out_c = dec_split.process(x[777:])
    out_combined = np.concatenate([out_a, out_b, out_c])

    np.testing.assert_allclose(out_combined, out_single, atol=1e-6)


def test_empty_input_returns_empty():
    dec = Decimator(factor=5, cutoff_hz=1000.0, input_sample_rate_hz=10000.0, num_taps=63)
    out = dec.process(np.empty(0, dtype=np.complex64))
    assert out.shape[0] == 0


def test_real_input_supported():
    dec = Decimator(factor=2, cutoff_hz=1000.0, input_sample_rate_hz=10000.0, num_taps=63)
    out = dec.process(np.ones(100, dtype=np.float32))
    assert out.dtype == np.float32
    assert out.shape[0] == 50
