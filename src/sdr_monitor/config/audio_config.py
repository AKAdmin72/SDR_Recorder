"""Параметры конвейера AM-демодуляции и записи WAV."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AudioConfig:
    """Настройки выделения канала, демодуляции, аудиофильтра и записи.

    Децимация выполняется в две ступени (см. ChannelExtractor/AudioResampler):
    sample_rate_hz -> channel_intermediate_sample_rate_hz -> audio_sample_rate_hz.
    Оба перехода должны делиться нацело — иначе простая целочисленная
    децимация (без дробного ресемплинга) невозможна.
    """

    channel_half_bandwidth_hz: float
    channel_intermediate_sample_rate_hz: int
    channel_filter_taps: int

    # Режим демодуляции: "am" | "fm". fm_deviation_hz используется только при
    # modulation_type="fm" (паспортная девиация FM-канала), но валидируется
    # всегда — проще, чем городить условную валидацию ради одного поля.
    modulation_type: str
    fm_deviation_hz: float

    voice_band_low_hz: float
    voice_band_high_hz: float
    voice_filter_order: int

    audio_sample_rate_hz: int
    audio_resample_cutoff_hz: float
    audio_resample_filter_taps: int

    # Во сколько раз домножить демодулированный сигнал перед записью в PCM16 —
    # своё значение на каждый режим демодуляции, потому что масштаб выхода
    # принципиально разный: AM-огибающая (np.abs) обычно даёт малые линейные
    # значения (~0.001-0.05 по наблюдениям на реальном приёме), а FM-выход
    # нормирован дискриминатором так, что полная девиация даёт амплитуду ~1.0.
    # Раздельные поля (а не один общий) означают, что переключение
    # modulation_type в конфиге не требует одновременной перенастройки
    # громкости — значение для неактивного режима просто не используется, но
    # не портится и не нуждается в повторном подборе при возврате к нему.
    am_pcm_full_scale_input: float
    fm_pcm_full_scale_input: float
    recordings_dir: Path

    # Минимальная длительность передачи, при которой она вообще пишется на диск —
    # аудио буферизуется в памяти, файл открывается только по достижении этого
    # порога. Если передача закрылась раньше — буфер отбрасывается без записи.
    min_recording_duration_s: float

    # Сколько ещё писать после закрытия детектором (естественное угасание
    # огибающей/хвост слова не обрезается резко).
    post_roll_duration_s: float

    def __post_init__(self) -> None:
        if self.channel_half_bandwidth_hz <= 0:
            raise ValueError(
                f"channel_half_bandwidth_hz={self.channel_half_bandwidth_hz} must be > 0"
            )
        if self.channel_intermediate_sample_rate_hz <= 2 * self.channel_half_bandwidth_hz:
            raise ValueError(
                f"channel_intermediate_sample_rate_hz="
                f"{self.channel_intermediate_sample_rate_hz} must be greater than "
                f"twice channel_half_bandwidth_hz={self.channel_half_bandwidth_hz} "
                f"(Nyquist theorem violated)"
            )
        if self.channel_filter_taps < 3:
            raise ValueError(f"channel_filter_taps={self.channel_filter_taps} must be >= 3")
        if self.modulation_type not in ("am", "fm"):
            raise ValueError(
                f"modulation_type={self.modulation_type!r} must be 'am' or 'fm'"
            )
        if self.fm_deviation_hz <= 0:
            raise ValueError(f"fm_deviation_hz={self.fm_deviation_hz} must be > 0")
        if self.fm_deviation_hz >= self.channel_intermediate_sample_rate_hz / 2:
            raise ValueError(
                f"fm_deviation_hz={self.fm_deviation_hz} must be less than half of "
                f"channel_intermediate_sample_rate_hz="
                f"{self.channel_intermediate_sample_rate_hz} (Nyquist ambiguity "
                "in the quadrature detector)"
            )
        if self.voice_band_low_hz <= 0 or self.voice_band_low_hz >= self.voice_band_high_hz:
            raise ValueError(
                f"voice_band_low_hz={self.voice_band_low_hz} must be > 0 and < "
                f"voice_band_high_hz={self.voice_band_high_hz}"
            )
        if self.voice_band_high_hz >= self.channel_intermediate_sample_rate_hz / 2:
            raise ValueError(
                f"voice_band_high_hz={self.voice_band_high_hz} must be less than half of "
                f"channel_intermediate_sample_rate_hz={self.channel_intermediate_sample_rate_hz}"
            )
        if self.voice_filter_order < 1:
            raise ValueError(f"voice_filter_order={self.voice_filter_order} must be >= 1")
        if self.audio_sample_rate_hz <= 0:
            raise ValueError(f"audio_sample_rate_hz={self.audio_sample_rate_hz} must be > 0")
        if self.audio_resample_cutoff_hz <= 0 or (
            self.audio_resample_cutoff_hz >= self.audio_sample_rate_hz / 2
        ):
            raise ValueError(
                f"audio_resample_cutoff_hz={self.audio_resample_cutoff_hz} must be in "
                f"(0, audio_sample_rate_hz/2={self.audio_sample_rate_hz / 2})"
            )
        if self.audio_resample_filter_taps < 3:
            raise ValueError(
                f"audio_resample_filter_taps={self.audio_resample_filter_taps} must be >= 3"
            )
        if self.am_pcm_full_scale_input <= 0:
            raise ValueError(
                f"am_pcm_full_scale_input={self.am_pcm_full_scale_input} must be > 0"
            )
        if self.fm_pcm_full_scale_input <= 0:
            raise ValueError(
                f"fm_pcm_full_scale_input={self.fm_pcm_full_scale_input} must be > 0"
            )
        if self.min_recording_duration_s < 0:
            raise ValueError(
                f"min_recording_duration_s={self.min_recording_duration_s} must be >= 0"
            )
        if self.post_roll_duration_s < 0:
            raise ValueError(
                f"post_roll_duration_s={self.post_roll_duration_s} must be >= 0"
            )

    @property
    def pcm_full_scale_input(self) -> float:
        """Значение, актуальное для текущего modulation_type — этим полем
        пользуется ChannelRecorder/WaveRecorder, не зная о режиме."""
        return self.am_pcm_full_scale_input if self.modulation_type == "am" else self.fm_pcm_full_scale_input
