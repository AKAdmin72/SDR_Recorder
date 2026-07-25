"""Потоковая запись одной передачи в отдельный WAV-файл."""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

_SAMPLE_WIDTH_BYTES = 2  # 16-бит PCM
_PCM16_MAX = 32767.0
_PCM16_MIN = -32768.0


class WaveRecorder:
    """Открывает WAV-файл в конструкторе, пишет чанками, закрывает по close().

    16-бит PCM моно — самый совместимый формат для голосовых записей,
    stdlib `wave` пишет корректный заголовок при close() без буферизации
    всего файла в памяти.
    """

    def __init__(self, file_path: Path, sample_rate_hz: int, pcm_full_scale_input: float) -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        self._pcm_full_scale_input = pcm_full_scale_input
        self._wave_file = wave.open(str(file_path), "wb")
        self._wave_file.setnchannels(1)
        self._wave_file.setsampwidth(_SAMPLE_WIDTH_BYTES)
        self._wave_file.setframerate(sample_rate_hz)

    def write(self, audio: np.ndarray) -> None:
        if audio.size == 0:
            return
        scaled = audio.astype(np.float64) / self._pcm_full_scale_input * _PCM16_MAX
        clipped = np.clip(scaled, _PCM16_MIN, _PCM16_MAX)
        self._wave_file.writeframes(clipped.astype(np.int16).tobytes())

    def close(self) -> None:
        self._wave_file.close()
