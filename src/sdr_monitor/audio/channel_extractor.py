"""Выделение одного узкополосного канала из широкополосного IQ-потока."""

from __future__ import annotations

import numpy as np

from sdr_monitor.config.audio_config import AudioConfig
from sdr_monitor.config.radio_config import RadioConfig
from sdr_monitor.dsp.decimator import Decimator


class ChannelExtractor:
    """Переносит канал на 0 Гц и децимирует до channel_intermediate_sample_rate_hz.

    Перенос — умножение на комплексную экспоненту, фаза которой считается
    напрямую из абсолютного sample_index блока (не накопительный NCO между
    блоками) — тот же принцип, что уже используется в проекте для
    sample-based меток времени: исключает дрейф фазы на длинных сессиях и
    не требует хранения фазового состояния между блоками.
    """

    def __init__(
        self, radio_config: RadioConfig, audio_config: AudioConfig, channel_frequency_hz: float
    ) -> None:
        factor = radio_config.sample_rate_hz / audio_config.channel_intermediate_sample_rate_hz
        if not factor.is_integer():
            raise ValueError(
                f"sample_rate_hz={radio_config.sample_rate_hz} is not evenly divisible by "
                f"channel_intermediate_sample_rate_hz="
                f"{audio_config.channel_intermediate_sample_rate_hz}"
            )

        self._sample_rate_hz = radio_config.sample_rate_hz
        self._delta_hz = channel_frequency_hz - radio_config.center_frequency_hz
        self._decimator = Decimator(
            factor=int(factor),
            cutoff_hz=audio_config.channel_half_bandwidth_hz,
            input_sample_rate_hz=radio_config.sample_rate_hz,
            num_taps=audio_config.channel_filter_taps,
        )

    def process(self, samples: np.ndarray, sample_index: int) -> np.ndarray:
        """Переносит и децимирует один чанк сырых IQ-отсчётов начиная с sample_index."""
        if samples.size == 0:
            return np.empty(0, dtype=np.complex64)

        n = np.arange(sample_index, sample_index + samples.shape[0], dtype=np.int64)
        phase = -2.0 * np.pi * self._delta_hz * n.astype(np.float64) / self._sample_rate_hz
        shifted = samples * np.exp(1j * phase).astype(np.complex64)

        return self._decimator.process(shifted)
