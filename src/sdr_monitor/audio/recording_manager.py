"""Оркестратор записи: открывает/закрывает ChannelRecorder по событиям детектора."""

from __future__ import annotations

import logging

from sdr_monitor.acquisition.iq_block import IQBlock
from sdr_monitor.audio.channel_recorder import ChannelRecorder
from sdr_monitor.config.audio_config import AudioConfig
from sdr_monitor.config.radio_config import RadioConfig
from sdr_monitor.detection.active_signal import ActiveSignal
from sdr_monitor.detection.detected_signal import DetectedSignal

_logger = logging.getLogger(__name__)


class RecordingManager:
    """Держит по одному ChannelRecorder на каждый сейчас открытый (CONFIRMED) трек,
    плюс на треки, у которых детектор уже закрыл передачу, но ChannelRecorder ещё
    дописывает post-roll (см. ChannelRecorder._RecorderState.CLOSING).

    Не знает ничего о детекции сигналов сама — только реагирует на события,
    которые ей передают (см. on_active_signals/on_signal_finalized), и
    прогоняет через все открытые каналы каждый пришедший IQBlock.
    """

    def __init__(self, audio_config: AudioConfig, radio_config: RadioConfig) -> None:
        self._audio_config = audio_config
        self._radio_config = radio_config
        self._recorders: dict[int, ChannelRecorder] = {}

    def on_active_signals(self, active_signals: list[ActiveSignal]) -> None:
        """Создаёт ChannelRecorder для треков, впервые появившихся среди активных.

        Сам файл на диске при этом ещё не открывается — см. ChannelRecorder:
        аудио буферизуется в памяти, пока трек не проживёт min_recording_duration_s.
        """
        for signal in active_signals:
            if signal.track_id in self._recorders:
                continue
            self._recorders[signal.track_id] = ChannelRecorder.create(
                self._audio_config,
                self._radio_config,
                signal.track_id,
                signal.center_frequency_hz,
                signal.start_time_utc,
            )

    def on_signal_finalized(self, signal: DetectedSignal) -> bool:
        """Детектор закрыл трек — переводит ChannelRecorder в режим post-roll
        (или отбрасывает буфер, если передача не набрала min_recording_duration_s).

        Возвращает True, если по этому треку был/будет сохранён WAV-файл —
        вызывающий код (GUI) использует это, чтобы не показывать в истории
        передачи короче min_recording_duration_s, для которых файл не создан.
        """
        recorder = self._recorders.get(signal.track_id)
        if recorder is None:
            return False
        was_recorded = recorder.begin_closing()
        if recorder.is_done:
            del self._recorders[signal.track_id]
        return was_recorded

    def process_block(self, block: IQBlock) -> None:
        done_track_ids = []
        for track_id, recorder in self._recorders.items():
            recorder.process(block)
            if recorder.is_done:
                done_track_ids.append(track_id)
        for track_id in done_track_ids:
            del self._recorders[track_id]

    def close_all(self) -> None:
        for recorder in self._recorders.values():
            recorder.close_immediately()
        self._recorders.clear()
