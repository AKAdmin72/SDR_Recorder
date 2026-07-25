"""Финальная децимация аудио до целевой частоты записи WAV."""

from __future__ import annotations

import numpy as np

from sdr_monitor.config.audio_config import AudioConfig
from sdr_monitor.dsp.decimator import Decimator


class AudioResampler:
    """Децимирует вещественное аудио с channel_intermediate_sample_rate_hz до
    audio_sample_rate_hz — ступень 2 общей двухступенчатой децимации (см.
    ChannelExtractor для ступени 1 и обоснование разбиения на две ступени).
    """

    def __init__(self, audio_config: AudioConfig) -> None:
        factor = audio_config.channel_intermediate_sample_rate_hz / audio_config.audio_sample_rate_hz
        if not factor.is_integer():
            raise ValueError(
                f"channel_intermediate_sample_rate_hz="
                f"{audio_config.channel_intermediate_sample_rate_hz} is not evenly divisible by "
                f"audio_sample_rate_hz={audio_config.audio_sample_rate_hz}"
            )

        self._decimator = Decimator(
            factor=int(factor),
            cutoff_hz=audio_config.audio_resample_cutoff_hz,
            input_sample_rate_hz=audio_config.channel_intermediate_sample_rate_hz,
            num_taps=audio_config.audio_resample_filter_taps,
        )

    def process(self, audio: np.ndarray) -> np.ndarray:
        return self._decimator.process(audio)
