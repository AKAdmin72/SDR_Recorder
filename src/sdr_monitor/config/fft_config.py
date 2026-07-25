"""Параметры FFT-анализа."""

from __future__ import annotations

from dataclasses import dataclass

_SUPPORTED_WINDOWS = frozenset({"hann", "hamming", "blackmanharris", "rectangular"})

_MIN_FFT_SIZE = 64
_MAX_FFT_SIZE = 65536


def _is_power_of_two(value: int) -> bool:
    return value > 0 and (value & (value - 1)) == 0


@dataclass(frozen=True, slots=True)
class FFTConfig:
    """Настройки потокового FFT-анализа спектра."""

    fft_size: int
    window_type: str
    averaging_count: int
    dc_notch_bins: int

    def __post_init__(self) -> None:
        if not _is_power_of_two(self.fft_size):
            raise ValueError(f"fft_size={self.fft_size} must be a power of two")
        if not _MIN_FFT_SIZE <= self.fft_size <= _MAX_FFT_SIZE:
            raise ValueError(
                f"fft_size={self.fft_size} out of range [{_MIN_FFT_SIZE}, {_MAX_FFT_SIZE}]"
            )
        if self.window_type not in _SUPPORTED_WINDOWS:
            raise ValueError(
                f"window_type={self.window_type!r} is not one of {sorted(_SUPPORTED_WINDOWS)}"
            )
        if self.averaging_count < 1:
            raise ValueError(f"averaging_count={self.averaging_count} must be >= 1")
        if self.dc_notch_bins < 0:
            raise ValueError(f"dc_notch_bins={self.dc_notch_bins} must be >= 0")
        if self.dc_notch_bins >= self.fft_size // 2:
            raise ValueError(
                f"dc_notch_bins={self.dc_notch_bins} is too large for fft_size={self.fft_size}"
            )
