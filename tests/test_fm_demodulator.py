import numpy as np

from sdr_monitor.audio.fm_demodulator import FmDemodulator

_SAMPLE_RATE = 80_000.0
_DEVIATION = 5_000.0


def _tone(freq_hz: float, n_samples: int) -> np.ndarray:
    n = np.arange(n_samples)
    return np.exp(1j * 2 * np.pi * freq_hz * n / _SAMPLE_RATE).astype(np.complex64)


def test_recovers_constant_frequency_offset():
    demod = FmDemodulator(sample_rate_hz=_SAMPLE_RATE, deviation_hz=_DEVIATION)
    f0 = _DEVIATION / 2
    samples = _tone(f0, 1000)

    result = demod.process(samples)

    # Первый отсчёт использует холодный старт (prev_sample=0) и не показателен.
    np.testing.assert_allclose(result[1:], 0.5, atol=1e-4)
    assert result.dtype == np.float32


def test_zero_frequency_gives_near_zero_output():
    demod = FmDemodulator(sample_rate_hz=_SAMPLE_RATE, deviation_hz=_DEVIATION)
    samples = _tone(0.0, 500)

    result = demod.process(samples)

    np.testing.assert_allclose(result[1:], 0.0, atol=1e-6)


def test_phase_continuous_across_chunk_boundary():
    demod = FmDemodulator(sample_rate_hz=_SAMPLE_RATE, deviation_hz=_DEVIATION)
    f0 = _DEVIATION / 3
    full = _tone(f0, 1000)

    first = demod.process(full[:500])
    second = demod.process(full[500:])
    combined = np.concatenate([first, second])

    expected = f0 / _DEVIATION
    # Всё, кроме самого первого отсчёта потока (холодный старт), должно быть
    # стабильно ровно expected — включая сам стык чанков на индексе 500,
    # что и подтверждает перенос состояния (_prev_sample) между вызовами.
    np.testing.assert_allclose(combined[1:], expected, atol=1e-4)


def test_empty_input_returns_empty_output():
    demod = FmDemodulator(sample_rate_hz=_SAMPLE_RATE, deviation_hz=_DEVIATION)

    result = demod.process(np.empty(0, dtype=np.complex64))

    assert result.size == 0
    assert result.dtype == np.float32
