"""Параметры радиотракта RTL-SDR (RTL2832U + тюнер, обычно R820T/R820T2)."""

from __future__ import annotations

from dataclasses import dataclass

from sdr_monitor.config.radio_config import RadioConfig

# Практический диапазон тюнера R820T/R820T2 (используется librtlsdr/rtl-sdr).
_MIN_FREQUENCY_HZ = 24_000_000
_MAX_FREQUENCY_HZ = 1_766_000_000

# Устойчивый диапазон частоты дискретизации RTL2832U (за пределами он тоже
# формально принимается драйвером, но даёт заметные потери отсчётов).
_MIN_SAMPLE_RATE_HZ = 225_001
_MAX_SAMPLE_RATE_HZ = 3_200_000

# gain_db не сверяется с точным списком поддерживаемых тюнером значений —
# этот список (rtlsdr_get_tuner_gains) читается только с реального устройства
# в рантайме и на этапе валидации конфига недоступен. RtlSdrDevice сам
# подбирает ближайшее поддерживаемое значение и логирует, если оно отличается
# от запрошенного. Здесь только защита от заведомо бессмысленных значений.
_MIN_GAIN_DB = 0.0
_MAX_GAIN_DB = 60.0


@dataclass(frozen=True, slots=True)
class RtlSdrRadioConfig(RadioConfig):
    """Настройки приёмника RTL-SDR: общие поля RadioConfig + усиление/AGC/буферизация."""

    gain_db: float
    agc_enabled: bool
    freq_correction_ppm: int
    read_async_buffer_count: int
    read_async_buffer_length: int

    def __post_init__(self) -> None:
        # Zero-arg super() ломается в slots=True dataclass-подклассах (decorator
        # пересоздаёт класс, __class__ cell ссылается на старый) — используем
        # явную форму.
        super(RtlSdrRadioConfig, self).__post_init__()
        if not _MIN_FREQUENCY_HZ <= self.center_frequency_hz <= _MAX_FREQUENCY_HZ:
            raise ValueError(
                f"center_frequency_hz={self.center_frequency_hz} out of range for "
                f"RTL-SDR [{_MIN_FREQUENCY_HZ}, {_MAX_FREQUENCY_HZ}]"
            )
        if not _MIN_SAMPLE_RATE_HZ <= self.sample_rate_hz <= _MAX_SAMPLE_RATE_HZ:
            raise ValueError(
                f"sample_rate_hz={self.sample_rate_hz} out of range for "
                f"RTL-SDR [{_MIN_SAMPLE_RATE_HZ}, {_MAX_SAMPLE_RATE_HZ}]"
            )
        if not _MIN_GAIN_DB <= self.gain_db <= _MAX_GAIN_DB:
            raise ValueError(
                f"gain_db={self.gain_db} out of reasonable range "
                f"[{_MIN_GAIN_DB}, {_MAX_GAIN_DB}]"
            )
        if self.read_async_buffer_count < 1:
            raise ValueError(
                f"read_async_buffer_count={self.read_async_buffer_count} must be >= 1"
            )
        if self.read_async_buffer_length <= 0 or self.read_async_buffer_length % 512 != 0:
            raise ValueError(
                f"read_async_buffer_length={self.read_async_buffer_length} must be "
                "positive and a multiple of 512 (librtlsdr requirement)"
            )
