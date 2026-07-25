"""Не бенчмарк с абсолютным порогом (нестабильно в CI) — относительное
сравнение с заведомо неэффективной эталонной реализацией (filter всего
блока -> отбросить лишнее), чтобы поймать регресс обратно к O(N) вместо
O(N/factor), но с большим запасом по марже, чтобы не флеймить на шумной машине.
"""

import time

import numpy as np
import pytest
from scipy.signal import firwin, lfilter

from sdr_monitor.dsp.decimator import Decimator

_FACTOR = 25
_NUM_TAPS = 127
_INPUT_SAMPLE_RATE_HZ = 2_000_000.0
_CUTOFF_HZ = 8_000.0
_N_SAMPLES = 131_072  # реальный размер блока RTL-SDR при read_async_buffer_length=262_144
_MIN_SPEEDUP = 3.0  # реально ожидается ~10-20x, берём с большим запасом
_REPEATS = 5  # минимум по нескольким повторам — меньше шума от разовых всплесков


def _naive_filter_then_slice(taps: np.ndarray, x: np.ndarray, phase: int = 0) -> np.ndarray:
    """Старая реализация Decimator "в лоб" — фильтруем всё, потом прореживаем."""
    filtered = lfilter(taps, [1.0], x)
    offset = (-phase) % _FACTOR
    return filtered[offset :: _FACTOR]


def _best_of(n: int, fn) -> float:
    return min(_time_call(fn) for _ in range(n))


def _time_call(fn) -> float:
    start = time.perf_counter()
    fn()
    return time.perf_counter() - start


def test_decimator_is_significantly_faster_than_naive_filter_then_slice():
    rng = np.random.default_rng(42)
    x = (rng.standard_normal(_N_SAMPLES) + 1j * rng.standard_normal(_N_SAMPLES)).astype(
        np.complex64
    )
    taps = firwin(_NUM_TAPS, _CUTOFF_HZ, fs=_INPUT_SAMPLE_RATE_HZ)

    naive_elapsed = _best_of(_REPEATS, lambda: _naive_filter_then_slice(taps, x))

    dec = Decimator(
        factor=_FACTOR,
        cutoff_hz=_CUTOFF_HZ,
        input_sample_rate_hz=_INPUT_SAMPLE_RATE_HZ,
        num_taps=_NUM_TAPS,
    )
    # первый вызов прогревает self._history/дополнительные аллокации — не мерим его
    dec.process(x[:1000])
    new_elapsed = _best_of(_REPEATS, lambda: dec.process(x))

    speedup = naive_elapsed / new_elapsed
    assert speedup >= _MIN_SPEEDUP, (
        f"Decimator.process() всего в {speedup:.1f}x быстрее наивной "
        f"filter-then-slice реализации (ожидалось >= {_MIN_SPEEDUP}x) — "
        "похоже на регресс к O(N) вместо O(N/factor)"
    )


@pytest.mark.parametrize("n_calls", [1, 2, 3])
def test_output_matches_naive_reference_across_repeated_calls(n_calls):
    # Не только быстрее — но и то же самое значение, что наивная реализация
    # на эквивалентном непрерывном потоке (защита от "быстро, но неверно").
    rng = np.random.default_rng(7)
    chunks = [
        (rng.standard_normal(4000) + 1j * rng.standard_normal(4000)).astype(np.complex64)
        for _ in range(n_calls)
    ]
    full = np.concatenate(chunks)

    dec = Decimator(
        factor=_FACTOR, cutoff_hz=_CUTOFF_HZ, input_sample_rate_hz=_INPUT_SAMPLE_RATE_HZ,
        num_taps=_NUM_TAPS,
    )
    actual = np.concatenate([dec.process(chunk) for chunk in chunks])
    taps = firwin(_NUM_TAPS, _CUTOFF_HZ, fs=_INPUT_SAMPLE_RATE_HZ)
    expected = _naive_filter_then_slice(taps, full)

    np.testing.assert_allclose(actual, expected, atol=1e-4)
