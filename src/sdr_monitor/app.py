"""Точка входа приложения: приём, детекция и запись передач авиадиапазона.

Полный конвейер один и тот же в обоих режимах: SDR -> IQStreamReader ->
FFTProcessor -> NoiseFloorEstimator -> SignalDetector -> RecordingManager
(ChannelExtractor -> демодулятор (AM/FM) -> AudioFilter -> AudioResampler ->
WaveRecorder). Различается только то, что показывает результат:

- GUI (по умолчанию): live-отображение в окне (MonitorWindow), работает до
  закрытия окна.
- --headless: без окна, для фоновой записи (например, на сервере без
  дисплея) — работает до Ctrl+C или до --duration секунд, если указано.
"""

from __future__ import annotations

import argparse
import logging
import queue
import time
from pathlib import Path

from sdr_monitor.acquisition.iq_stream import IQStreamReader
from sdr_monitor.audio.recording_manager import RecordingManager
from sdr_monitor.config.app_config import AppConfig
from sdr_monitor.config.config_loader import load_config
from sdr_monitor.config_selector import select_config_path
from sdr_monitor.detection.detected_signal import DetectedSignal
from sdr_monitor.detection.signal_detector import SignalDetector
from sdr_monitor.dsp.fft_processor import FFTProcessor
from sdr_monitor.dsp.noise_floor_estimator import NoiseFloorEstimator
from sdr_monitor.hardware.sdr_device import SdrDevice
from sdr_monitor.hardware.sdr_factory import create_sdr_device
from sdr_monitor.logging_setup import configure_logging

_logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CONFIG_DIR = _PROJECT_ROOT / "config"
_QUEUE_POLL_TIMEOUT_S = 0.5


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SDR Monitor — receives, detects, and records aviation-band transmissions"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to the TOML config. If omitted, prompts interactively from "
        "config/ when more than one file is present.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="No GUI — background mode (by default a live-view window is opened)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Time limit in headless mode, seconds (default — run until Ctrl+C). "
        "Ignored in GUI mode, the window is closed manually.",
    )
    return parser.parse_args()


def _build_pipeline(app_config: AppConfig, device: SdrDevice):
    reader = IQStreamReader(device, app_config.radio, app_config.acquisition)
    processor = FFTProcessor(app_config.radio, app_config.fft)
    estimator = NoiseFloorEstimator(app_config.noise_floor)
    detector = SignalDetector(app_config.detection)
    recording_manager = RecordingManager(app_config.audio, app_config.radio)
    return reader, processor, estimator, detector, recording_manager


def run_gui(config_path: Path) -> None:
    from sdr_monitor.display.monitor_window import MonitorWindow

    app_config = load_config(config_path)
    configure_logging(app_config.logging.level)
    _logger.info("Configuration loaded from %s", config_path)

    with create_sdr_device(app_config.radio) as device:
        reader, processor, estimator, detector, recording_manager = _build_pipeline(
            app_config, device
        )
        reader.start()

        window = MonitorWindow(
            app_config.display,
            app_config.radio,
            app_config.detection,
            app_config.fft,
            reader,
            processor,
            estimator,
            detector,
            recording_manager,
            config_path,
        )
        window.run()  # блокируется до закрытия окна; окно само останавливает reader


def run_headless(config_path: Path, duration_s: float | None) -> None:
    app_config = load_config(config_path)
    configure_logging(app_config.logging.level)
    _logger.info("Configuration loaded from %s", config_path)
    _logger.info("Recordings will be saved to %s", app_config.audio.recordings_dir.resolve())
    _logger.info(
        "Headless mode: %s",
        f"stopping after {duration_s:.0f}s" if duration_s is not None else "running until Ctrl+C",
    )

    with create_sdr_device(app_config.radio) as device:
        reader, processor, estimator, detector, recording_manager = _build_pipeline(
            app_config, device
        )
        reader.start()

        start_time = time.monotonic()
        next_stats_at = start_time + app_config.acquisition.stats_log_interval_s
        total_frames = 0
        total_detections = 0

        try:
            while duration_s is None or time.monotonic() - start_time < duration_s:
                try:
                    block = reader.get_block(timeout=_QUEUE_POLL_TIMEOUT_S)
                except queue.Empty:
                    continue

                for frame in processor.process(block):
                    total_frames += 1
                    estimator.update(frame)
                    if not estimator.is_ready:
                        continue
                    noise_floor_db = estimator.noise_floor_db()

                    for signal in detector.update(frame, noise_floor_db):
                        total_detections += 1
                        _log_signal(signal)
                        recording_manager.on_signal_finalized(signal)

                    recording_manager.on_active_signals(detector.active_signals())

                recording_manager.process_block(block)

                now = time.monotonic()
                if now >= next_stats_at:
                    _logger.info(
                        "t=%.1fs: frames=%d, blocks dropped=%d, "
                        "transmissions detected=%d, recordings active=%d",
                        now - start_time,
                        total_frames,
                        reader.dropped_blocks,
                        total_detections,
                        len(detector.active_signals()),
                    )
                    next_stats_at = now + app_config.acquisition.stats_log_interval_s
        except KeyboardInterrupt:
            _logger.info("Stopped by Ctrl+C")
        finally:
            reader.stop()

        for signal in detector.flush():
            total_detections += 1
            _logger.info("(transmission still open at end of session)")
            _log_signal(signal)
            recording_manager.on_signal_finalized(signal)

        recording_manager.close_all()

    _logger.info(
        "Summary: duration=%.1fs, frames=%d, blocks received=%d, blocks dropped=%d, "
        "transmissions detected=%d",
        time.monotonic() - start_time,
        total_frames,
        reader.received_blocks,
        reader.dropped_blocks,
        total_detections,
    )


def _log_signal(signal: DetectedSignal) -> None:
    _logger.info(
        "TRANSMISSION: track_id=%d, %.4f MHz, level=%.1f dB, SNR=%.1f dB, duration=%.3fs",
        signal.track_id,
        signal.center_frequency_hz / 1e6,
        signal.peak_level_db,
        signal.peak_snr_db,
        signal.duration_s,
    )


def main() -> None:
    args = _parse_args()
    config_path = select_config_path(_CONFIG_DIR, args.config)
    if args.headless:
        run_headless(config_path, args.duration)
    else:
        run_gui(config_path)


if __name__ == "__main__":
    main()
