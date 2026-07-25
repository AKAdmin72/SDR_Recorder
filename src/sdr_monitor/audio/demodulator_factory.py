"""Выбор конкретного демодулятора по AudioConfig.modulation_type."""

from __future__ import annotations

from sdr_monitor.audio.am_demodulator import AmDemodulator
from sdr_monitor.audio.demodulator import Demodulator
from sdr_monitor.audio.fm_demodulator import FmDemodulator
from sdr_monitor.config.audio_config import AudioConfig


def create_demodulator(audio_config: AudioConfig) -> Demodulator:
    if audio_config.modulation_type == "am":
        return AmDemodulator()
    if audio_config.modulation_type == "fm":
        return FmDemodulator(
            sample_rate_hz=audio_config.channel_intermediate_sample_rate_hz,
            deviation_hz=audio_config.fm_deviation_hz,
        )
    raise ValueError(f"Unknown modulation_type={audio_config.modulation_type!r}")
