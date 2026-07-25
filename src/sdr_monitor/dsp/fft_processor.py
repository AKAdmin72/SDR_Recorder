"""Потоковый FFT-анализ: нарезка IQ-потока на окна с усреднением мощности."""

from __future__ import annotations

import logging
from datetime import datetime

import numpy as np
from scipy.fft import fft, fftfreq, fftshift

from sdr_monitor.acquisition.iq_block import IQBlock
from sdr_monitor.config.fft_config import FFTConfig
from sdr_monitor.config.radio_config import RadioConfig
from sdr_monitor.dsp.spectral_frame import SpectralFrame
from sdr_monitor.dsp.windows import get_window

_logger = logging.getLogger(__name__)

_POWER_FLOOR = 1e-20  # защита от log10(0), не физический параметр


class FFTProcessor:
    """Нарезает поток IQ-отсчётов на FFT-окна, усредняет мощность, выдаёт SpectralFrame.

    IQBlock-и могут быть любого размера, не обязательно кратного fft_size —
    остаток отсчётов переносится между вызовами process(). Если в потоке
    обнаруживается разрыв номеров отсчётов (например, IQStreamReader дропнул
    блок из-за переполнения очереди), накопленный остаток и текущая группа
    усреднения сбрасываются — иначе несмежные отсчёты склеились бы в одно
    окно, дав недостоверный спектр.
    """

    def __init__(self, radio_config: RadioConfig, fft_config: FFTConfig) -> None:
        self._fft_size = fft_config.fft_size
        self._averaging_count = fft_config.averaging_count
        self._dc_notch_bins = fft_config.dc_notch_bins
        self._sample_rate_hz = radio_config.sample_rate_hz

        self._window = get_window(fft_config.window_type, fft_config.fft_size)
        self._window_power_sum = float(np.sum(self._window.astype(np.float64) ** 2))

        baseband_freqs = fftshift(
            fftfreq(fft_config.fft_size, d=1.0 / radio_config.sample_rate_hz)
        )
        self._frequencies_hz = baseband_freqs + radio_config.center_frequency_hz

        self._pending_samples = np.empty(0, dtype=np.complex64)
        self._pending_start_index = 0
        self._pending_start_valid = False

        self._power_accumulator = np.zeros(fft_config.fft_size, dtype=np.float64)
        self._averaging_group_count = 0
        self._averaging_group_start_index = 0

    def process(self, block: IQBlock) -> list[SpectralFrame]:
        """Обрабатывает один IQBlock, возвращает 0+ готовых SpectralFrame."""
        self._resync_if_discontinuous(block.sample_index)

        if not self._pending_start_valid:
            self._pending_start_index = block.sample_index
            self._pending_start_valid = True

        if self._pending_samples.size == 0:
            combined = block.samples
        else:
            combined = np.concatenate((self._pending_samples, block.samples))
        combined_start_index = self._pending_start_index

        n_complete_windows = combined.shape[0] // self._fft_size
        frames: list[SpectralFrame] = []

        for window_index in range(n_complete_windows):
            offset = window_index * self._fft_size
            window_samples = combined[offset : offset + self._fft_size]
            window_start_index = combined_start_index + offset

            frame = self._consume_window(
                window_samples, window_start_index, block.stream_start_utc
            )
            if frame is not None:
                frames.append(frame)

        consumed = n_complete_windows * self._fft_size
        self._pending_samples = combined[consumed:].copy()
        self._pending_start_index = combined_start_index + consumed

        return frames

    def _resync_if_discontinuous(self, block_sample_index: int) -> None:
        if not self._pending_start_valid:
            return
        expected_start_index = self._pending_start_index + self._pending_samples.shape[0]
        if block_sample_index == expected_start_index:
            return
        _logger.warning(
            "Discontinuity in sample stream (expected sample_index=%d, got %d) — "
            "resetting accumulated remainder and current averaging group",
            expected_start_index,
            block_sample_index,
        )
        self._pending_samples = np.empty(0, dtype=np.complex64)
        self._pending_start_valid = False
        self._power_accumulator = np.zeros(self._fft_size, dtype=np.float64)
        self._averaging_group_count = 0

    def _consume_window(
        self, samples: np.ndarray, window_start_index: int, stream_start_utc: datetime
    ) -> SpectralFrame | None:
        if self._averaging_group_count == 0:
            self._averaging_group_start_index = window_start_index

        spectrum = fftshift(fft(samples * self._window))
        power = spectrum.real.astype(np.float64) ** 2 + spectrum.imag.astype(np.float64) ** 2
        power /= self._fft_size * self._window_power_sum
        self._power_accumulator += power
        self._averaging_group_count += 1

        if self._averaging_group_count < self._averaging_count:
            return None

        mean_power = self._power_accumulator / self._averaging_count
        if self._dc_notch_bins > 0:
            center = self._fft_size // 2
            half = self._dc_notch_bins
            mean_power[center - half : center + half + 1] = _POWER_FLOOR

        power_db = (10.0 * np.log10(mean_power + _POWER_FLOOR)).astype(np.float32)

        frame = SpectralFrame(
            frequencies_hz=self._frequencies_hz,
            power_db=power_db,
            start_sample_index=self._averaging_group_start_index,
            end_sample_index=window_start_index + self._fft_size,
            sample_rate_hz=self._sample_rate_hz,
            stream_start_utc=stream_start_utc,
        )

        self._power_accumulator = np.zeros(self._fft_size, dtype=np.float64)
        self._averaging_group_count = 0

        return frame
