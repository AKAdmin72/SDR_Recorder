"""Полосовой аудиофильтр после демодуляции (AM или FM)."""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfilt, sosfilt_zi

from sdr_monitor.config.audio_config import AudioConfig


class AudioFilter:
    """Полосовой Butterworth (voice_band_low_hz..voice_band_high_hz), потоковый.

    Один bandpass-фильтр решает сразу две задачи: убирает низкочастотное
    смещение (у AM — DC от постоянной составляющей несущей; у FM — возможный
    остаточный дрейф дискриминатора) и отсекает шум выше речевого диапазона —
    отдельные HP/LP фильтры для этого не нужны.
    """

    def __init__(self, audio_config: AudioConfig, input_sample_rate_hz: float) -> None:
        self._sos = butter(
            audio_config.voice_filter_order,
            [audio_config.voice_band_low_hz, audio_config.voice_band_high_hz],
            btype="bandpass",
            fs=input_sample_rate_hz,
            output="sos",
        )
        # Холодный старт (нулевое состояние): до начала записи сигнала не было.
        # sosfilt_zi() без масштабирования даёт состояние, соответствующее
        # единичному входу, поданному "всегда" — здесь это неверно.
        self._zi = np.zeros_like(sosfilt_zi(self._sos))

    def process(self, audio: np.ndarray) -> np.ndarray:
        if audio.size == 0:
            return np.empty(0, dtype=np.float32)
        filtered, self._zi = sosfilt(self._sos, audio, zi=self._zi)
        return filtered.astype(np.float32)
