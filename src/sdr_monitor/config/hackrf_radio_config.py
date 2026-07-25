"""Параметры радиотракта HackRF."""

from __future__ import annotations

from dataclasses import dataclass

from sdr_monitor.config.radio_config import RadioConfig

_MIN_FREQUENCY_HZ = 1_000_000
_MAX_FREQUENCY_HZ = 6_000_000_000

_MIN_SAMPLE_RATE_HZ = 2_000_000
_MAX_SAMPLE_RATE_HZ = 20_000_000

_VALID_LNA_GAINS_DB = frozenset(range(0, 41, 8))
_VALID_VGA_GAINS_DB = frozenset(range(0, 63, 2))


@dataclass(frozen=True, slots=True)
class HackRFRadioConfig(RadioConfig):
    """Настройки приёмника HackRF: общие поля RadioConfig + усиление LNA/VGA/AMP."""

    lna_gain_db: int
    vga_gain_db: int
    amp_enable: bool

    def __post_init__(self) -> None:
        # Zero-arg super() ломается в slots=True dataclass-подклассах (decorator
        # пересоздаёт класс, __class__ cell ссылается на старый) — используем
        # явную форму.
        super(HackRFRadioConfig, self).__post_init__()
        if not _MIN_FREQUENCY_HZ <= self.center_frequency_hz <= _MAX_FREQUENCY_HZ:
            raise ValueError(
                f"center_frequency_hz={self.center_frequency_hz} out of range for "
                f"HackRF [{_MIN_FREQUENCY_HZ}, {_MAX_FREQUENCY_HZ}]"
            )
        if not _MIN_SAMPLE_RATE_HZ <= self.sample_rate_hz <= _MAX_SAMPLE_RATE_HZ:
            raise ValueError(
                f"sample_rate_hz={self.sample_rate_hz} out of range for "
                f"HackRF [{_MIN_SAMPLE_RATE_HZ}, {_MAX_SAMPLE_RATE_HZ}]"
            )
        if self.lna_gain_db not in _VALID_LNA_GAINS_DB:
            raise ValueError(
                f"lna_gain_db={self.lna_gain_db} must be a multiple of 8 in the range 0-40"
            )
        if self.vga_gain_db not in _VALID_VGA_GAINS_DB:
            raise ValueError(
                f"vga_gain_db={self.vga_gain_db} must be a multiple of 2 in the range 0-62"
            )
