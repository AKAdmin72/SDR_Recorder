"""Полный конвейер записи одной передачи: канал -> демод -> фильтр -> ресемплинг -> WAV.

Состояния (см. _RecorderState):
  BUFFERING -> открыт трек, аудио копится в памяти, WAV ещё не создан.
  RECORDING -> буфер достиг min_recording_duration_s, WAV открыт, пишем сразу.
  CLOSING   -> детектор закрыл трек, дописываем post_roll_duration_s "на хвост".
  DONE      -> файл закрыт (или буфер отброшен, если так и не дошли до RECORDING).

Короткие передачи (не достигшие min_recording_duration_s к моменту закрытия)
никогда не создают файл — это и есть фильтр от шумовых всплесков.
"""

from __future__ import annotations

import enum
import logging
from datetime import datetime
from pathlib import Path

import numpy as np

from sdr_monitor.acquisition.iq_block import IQBlock
from sdr_monitor.audio.audio_filter import AudioFilter
from sdr_monitor.audio.audio_resampler import AudioResampler
from sdr_monitor.audio.channel_extractor import ChannelExtractor
from sdr_monitor.audio.demodulator import Demodulator
from sdr_monitor.audio.demodulator_factory import create_demodulator
from sdr_monitor.audio.wave_recorder import WaveRecorder
from sdr_monitor.config.audio_config import AudioConfig
from sdr_monitor.config.radio_config import RadioConfig

_logger = logging.getLogger(__name__)


class _RecorderState(enum.Enum):
    BUFFERING = enum.auto()
    RECORDING = enum.auto()
    CLOSING = enum.auto()
    DONE = enum.auto()


class ChannelRecorder:
    """Связывает ChannelExtractor -> AM -> AudioFilter -> AudioResampler -> WaveRecorder
    для одного трека — свои экземпляры и своё состояние на каждый активный канал.
    """

    def __init__(
        self,
        extractor: ChannelExtractor,
        demodulator: Demodulator,
        audio_filter: AudioFilter,
        resampler: AudioResampler,
        audio_config: AudioConfig,
        file_path: Path,
        track_id: int,
    ) -> None:
        self._extractor = extractor
        self._demodulator = demodulator
        self._audio_filter = audio_filter
        self._resampler = resampler
        self._audio_config = audio_config
        self._file_path = file_path
        self._track_id = track_id

        self._state = _RecorderState.BUFFERING
        self._buffered_chunks: list[np.ndarray] = []
        self._buffered_samples = 0
        self._wave_recorder: WaveRecorder | None = None
        self._post_roll_samples_remaining = 0

    @classmethod
    def create(
        cls,
        audio_config: AudioConfig,
        radio_config: RadioConfig,
        track_id: int,
        center_frequency_hz: float,
        start_time_utc: datetime,
    ) -> "ChannelRecorder":
        extractor = ChannelExtractor(radio_config, audio_config, center_frequency_hz)
        demodulator = create_demodulator(audio_config)
        audio_filter = AudioFilter(audio_config, audio_config.channel_intermediate_sample_rate_hz)
        resampler = AudioResampler(audio_config)
        file_path = _build_file_path(
            audio_config.recordings_dir, start_time_utc, center_frequency_hz
        )
        return cls(
            extractor, demodulator, audio_filter, resampler, audio_config, file_path, track_id
        )

    @property
    def is_done(self) -> bool:
        return self._state is _RecorderState.DONE

    def process(self, block: IQBlock) -> None:
        if self._state is _RecorderState.DONE:
            return

        channel_samples = self._extractor.process(block.samples, block.sample_index)
        if channel_samples.size == 0:
            return
        audio = self._demodulator.process(channel_samples)
        filtered = self._audio_filter.process(audio)
        resampled = self._resampler.process(filtered)
        if resampled.size == 0:
            return

        if self._state is _RecorderState.BUFFERING:
            self._buffered_chunks.append(resampled)
            self._buffered_samples += resampled.shape[0]
            min_samples = round(
                self._audio_config.min_recording_duration_s
                * self._audio_config.audio_sample_rate_hz
            )
            if self._buffered_samples >= min_samples:
                self._promote_to_recording()
            return

        self._wave_recorder.write(resampled)
        if self._state is _RecorderState.CLOSING:
            self._post_roll_samples_remaining -= resampled.shape[0]
            if self._post_roll_samples_remaining <= 0:
                self._finish()

    def begin_closing(self) -> bool:
        """Детектор закрыл трек. Отбрасывает буфер, если так и не набрали
        минимальную длительность, иначе переходит в CLOSING (пишет ещё post_roll).

        Возвращает True, если по этому треку файл на диске создан (или будет
        создан) — то есть сигнал прошёл тот же порог min_recording_duration_s,
        что и запись. Вызывающий код использует это, чтобы история в GUI
        показывала ровно те же передачи, что и сохранённые файлы.
        """
        if self._state is _RecorderState.BUFFERING:
            _logger.info(
                "Recording discarded (shorter than %.1fs): track_id=%d, file not created (%s)",
                self._audio_config.min_recording_duration_s,
                self._track_id,
                self._file_path.name,
            )
            self._state = _RecorderState.DONE
            return False
        if self._state is _RecorderState.RECORDING:
            self._post_roll_samples_remaining = round(
                self._audio_config.post_roll_duration_s * self._audio_config.audio_sample_rate_hz
            )
            self._state = _RecorderState.CLOSING
            if self._post_roll_samples_remaining <= 0:
                self._finish()
        return True

    def close_immediately(self) -> None:
        """Принудительное завершение (например, остановка приложения) — без
        дожидания post-roll. Буфер короче min_recording_duration_s всё равно
        отбрасывается, ради консистентности с обычным закрытием."""
        if self._state is _RecorderState.BUFFERING:
            self._state = _RecorderState.DONE
            return
        if self._wave_recorder is not None:
            self._wave_recorder.close()
        self._state = _RecorderState.DONE

    def _promote_to_recording(self) -> None:
        self._wave_recorder = WaveRecorder(
            self._file_path,
            self._audio_config.audio_sample_rate_hz,
            self._audio_config.pcm_full_scale_input,
        )
        for chunk in self._buffered_chunks:
            self._wave_recorder.write(chunk)
        self._buffered_chunks.clear()
        self._state = _RecorderState.RECORDING
        _logger.info("Recording started: track_id=%d -> %s", self._track_id, self._file_path)

    def _finish(self) -> None:
        self._wave_recorder.close()
        self._state = _RecorderState.DONE
        _logger.info("Recording finished: track_id=%d -> %s", self._track_id, self._file_path)


def _build_file_path(
    recordings_dir: Path, start_time_utc: datetime, center_frequency_hz: float
) -> Path:
    """Например: 2026-07-12_14-31-08_127900000.wav. Время — UTC (как весь проект)."""
    timestamp = start_time_utc.strftime("%Y-%m-%d_%H-%M-%S")
    frequency_hz = int(round(center_frequency_hz))
    return recordings_dir / f"{timestamp}_{frequency_hz}.wav"
