"""Загрузка AppConfig из TOML-файла."""

from __future__ import annotations

import tomllib
from pathlib import Path

from sdr_monitor.config.acquisition_config import AcquisitionConfig
from sdr_monitor.config.app_config import AppConfig
from sdr_monitor.config.audio_config import AudioConfig
from sdr_monitor.config.detection_config import DetectionConfig
from sdr_monitor.config.display_config import DisplayConfig
from sdr_monitor.config.fft_config import FFTConfig
from sdr_monitor.config.frequency_range import FrequencyRange
from sdr_monitor.config.hackrf_radio_config import HackRFRadioConfig
from sdr_monitor.config.logging_config import LoggingConfig
from sdr_monitor.config.noise_floor_config import NoiseFloorConfig
from sdr_monitor.config.radio_config import RadioConfig
from sdr_monitor.config.rtlsdr_radio_config import RtlSdrRadioConfig

_RADIO_CONFIG_BY_SDR_TYPE = {
    "hackrf": (HackRFRadioConfig, "hackrf"),
    "rtlsdr": (RtlSdrRadioConfig, "rtlsdr"),
}


def _build_radio_config(raw: dict, source_desc: str) -> RadioConfig:
    try:
        sdr_type = raw["sdr"]["type"]
    except KeyError as exc:
        raise ValueError(f"Config {source_desc} is missing section {exc}") from exc

    try:
        radio_cls, section_name = _RADIO_CONFIG_BY_SDR_TYPE[sdr_type]
    except KeyError:
        raise ValueError(
            f"Unknown sdr.type={sdr_type!r} in {source_desc}, "
            f"expected one of {sorted(_RADIO_CONFIG_BY_SDR_TYPE)}"
        ) from None

    try:
        radio_section = raw["radio"][section_name]
    except KeyError as exc:
        raise ValueError(
            f"Config {source_desc} is missing section [radio.{section_name}], "
            f"required for sdr.type={sdr_type!r}"
        ) from exc

    return radio_cls(**radio_section)


def load_config_from_text(text: str, source_desc: str) -> AppConfig:
    """Строит валидированный AppConfig из уже прочитанного текста TOML.

    Вынесено отдельно от load_config(), чтобы можно было провалидировать
    текст ДО записи на диск (например, в GUI-редакторе конфига — там текст
    правится в памяти поточечно, и невалидный результат не должен долетать
    до файла).

    Ошибки валидации отдельных секций (RadioConfig/AcquisitionConfig/LoggingConfig)
    пробрасываются как ValueError — конфигурация с некорректными параметрами
    не должна приводить к запуску приложения.

    Секция [radio.*], соответствующая [sdr].type, парсится и валидируется;
    остальные [radio.*] секции (если есть) читаются как обычные TOML-таблицы,
    но не участвуют — так переключение железа сводится к одной строке
    sdr.type без удаления/раскомментирования блоков.
    """
    raw = tomllib.loads(text)

    try:
        acquisition_section = raw["acquisition"]
        fft_section = raw["fft"]
        noise_floor_section = raw["noise_floor"]
        detection_section = raw["detection"]
        display_section = raw["display"]
        audio_section = raw["audio"]
        logging_section = raw["logging"]
    except KeyError as exc:
        raise ValueError(f"Config {source_desc} is missing section {exc}") from exc

    radio_config = _build_radio_config(raw, source_desc)

    detection_section = dict(detection_section)
    blacklisted_ranges = tuple(
        FrequencyRange(**entry) for entry in detection_section.pop("blacklisted_ranges", [])
    )

    audio_section = dict(audio_section)
    audio_section["recordings_dir"] = Path(audio_section["recordings_dir"])

    return AppConfig(
        radio=radio_config,
        acquisition=AcquisitionConfig(**acquisition_section),
        fft=FFTConfig(**fft_section),
        noise_floor=NoiseFloorConfig(**noise_floor_section),
        detection=DetectionConfig(blacklisted_ranges=blacklisted_ranges, **detection_section),
        display=DisplayConfig(**display_section),
        audio=AudioConfig(**audio_section),
        logging=LoggingConfig(**logging_section),
    )


def load_config(config_path: Path) -> AppConfig:
    """Читает TOML-файл конфигурации и строит валидированный AppConfig."""
    return load_config_from_text(config_path.read_text(encoding="utf-8"), str(config_path))
