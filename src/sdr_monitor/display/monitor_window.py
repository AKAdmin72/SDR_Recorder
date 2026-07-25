"""tkinter-окно живого отображения активных и завершённых передач.

Архитектурно однопоточное: root.mainloop() владеет главным потоком (обязательное
требование Tcl/Tk), а сам приём IQ обслуживается двумя периодическими таймерами
tkinter (root.after), а не отдельным потоком:
  - _pump()   — часто, неблокирующе вычерпывает очередь IQBlock и прогоняет
                конвейер FFT -> шумовой пол -> детектор. Виджеты не трогает.
  - _redraw() — редко, перерисовывает таблицы из уже посчитанного состояния.
Никакой синхронизации между потоками не требуется, потому что второго потока нет.
"""

from __future__ import annotations

import logging
import queue
import tkinter as tk
from collections import deque
from datetime import datetime
from pathlib import Path
from tkinter import ttk

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from sdr_monitor.acquisition.iq_stream import IQStreamReader
from sdr_monitor.audio.recording_manager import RecordingManager
from sdr_monitor.config.detection_config import DetectionConfig
from sdr_monitor.config.display_config import DisplayConfig
from sdr_monitor.config.fft_config import FFTConfig
from sdr_monitor.config.radio_config import RadioConfig
from sdr_monitor.config_editor import open_as_toplevel
from sdr_monitor.detection.active_signal import ActiveSignal
from sdr_monitor.detection.detected_signal import DetectedSignal
from sdr_monitor.detection.signal_detector import SignalDetector
from sdr_monitor.dsp.fft_processor import FFTProcessor
from sdr_monitor.dsp.noise_floor_estimator import NoiseFloorEstimator

_logger = logging.getLogger(__name__)

_ACTIVE_COLUMNS = ("freq", "level", "snr", "peak_level", "peak_snr", "elapsed")
_ACTIVE_HEADINGS = (
    "Freq, MHz",
    "Level, dB",
    "SNR, dB",
    "Peak, dB",
    "Peak SNR, dB",
    "Duration, s",
)

_HISTORY_COLUMNS = ("freq", "peak_level", "peak_snr", "start", "end", "duration")
_HISTORY_HEADINGS = (
    "Freq, MHz",
    "Peak, dB",
    "Peak SNR, dB",
    "Start",
    "End",
    "Duration, s",
)


class MonitorWindow:
    """Живое окно: спектр + таблица активных передач + история последних завершённых."""

    def __init__(
        self,
        display_config: DisplayConfig,
        radio_config: RadioConfig,
        detection_config: DetectionConfig,
        fft_config: FFTConfig,
        reader: IQStreamReader,
        processor: FFTProcessor,
        estimator: NoiseFloorEstimator,
        detector: SignalDetector,
        recording_manager: RecordingManager,
        config_path: Path,
    ) -> None:
        self._display_config = display_config
        self._detection_config = detection_config
        self._dc_notch_bins = fft_config.dc_notch_bins
        self._reader = reader
        self._processor = processor
        self._estimator = estimator
        self._detector = detector
        self._recording_manager = recording_manager
        self._config_path = config_path
        self._history: deque[DetectedSignal] = deque(maxlen=display_config.history_size)
        self._total_frames = 0
        self._closed = False

        self._spectrum_accumulator = _MaxHoldAccumulator()
        self._frequencies_hz: np.ndarray | None = None
        self._spectrum_autoscale_mask: np.ndarray | None = None

        self._root = tk.Tk()
        self._root.title(
            f"SDR Monitor — {radio_config.center_frequency_hz / 1e6:.3f} MHz / "
            f"{radio_config.sample_rate_hz / 1e6:.3f} Msps"
        )
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_toolbar()
        self._build_spectrum_panel()
        self._active_tree = self._build_table(
            "Active transmissions", _ACTIVE_COLUMNS, _ACTIVE_HEADINGS
        )
        self._history_tree = self._build_table(
            f"History (last {display_config.history_size})",
            _HISTORY_COLUMNS,
            _HISTORY_HEADINGS,
        )
        self._status_var = tk.StringVar(value="Starting...")
        ttk.Label(self._root, textvariable=self._status_var, anchor="w").pack(
            fill="x", padx=8, pady=(0, 8)
        )

    def _build_toolbar(self) -> None:
        toolbar = ttk.Frame(self._root)
        toolbar.pack(fill="x", padx=8, pady=(8, 0))
        ttk.Button(toolbar, text="Config...", command=self._open_config_editor).pack(side="left")

    def _open_config_editor(self) -> None:
        # Правит только файл на диске — рантайм-объекты уже запущенного
        # приложения (reader/processor/...) не трогает, поэтому открытие
        # безопасно в любой момент. Изменения требуют перезапуска приложения.
        open_as_toplevel(self._root, self._config_path)

    def _build_spectrum_panel(self) -> None:
        frame = ttk.LabelFrame(
            self._root, text="Spectrum (max-hold over redraw period)"
        )
        frame.pack(fill="both", expand=True, padx=8, pady=(8, 0))

        figure = Figure(figsize=(9, 3.2), dpi=100)
        self._spectrum_axes = figure.add_subplot(111)
        self._spectrum_axes.set_xlabel("Frequency, MHz")
        self._spectrum_axes.set_ylabel("Power, dB")
        (self._spectrum_power_line,) = self._spectrum_axes.plot(
            [], [], color="tab:blue", linewidth=1.0, label="Spectrum (max-hold)"
        )
        (self._spectrum_noise_line,) = self._spectrum_axes.plot(
            [], [], color="tab:gray", linewidth=1.0, label="Noise floor"
        )
        (self._spectrum_open_line,) = self._spectrum_axes.plot(
            [], [], color="tab:red", linewidth=1.0, linestyle="--", label="Open threshold"
        )
        (self._spectrum_close_line,) = self._spectrum_axes.plot(
            [], [], color="tab:orange", linewidth=1.0, linestyle="--", label="Close threshold"
        )
        for frequency_range in self._detection_config.blacklisted_ranges:
            self._spectrum_axes.axvspan(
                frequency_range.start_hz / 1e6,
                frequency_range.end_hz / 1e6,
                color="black",
                alpha=0.12,
                zorder=0,
            )
        self._spectrum_axes.legend(loc="upper right", fontsize=8)
        self._spectrum_axes.grid(True, linewidth=0.3)

        self._spectrum_canvas = FigureCanvasTkAgg(figure, master=frame)
        self._spectrum_canvas.get_tk_widget().pack(fill="both", expand=True)

    def _build_table(
        self, title: str, columns: tuple[str, ...], headings: tuple[str, ...]
    ) -> ttk.Treeview:
        frame = ttk.LabelFrame(self._root, text=title)
        frame.pack(fill="both", expand=True, padx=8, pady=(8, 0))

        tree = ttk.Treeview(frame, columns=columns, show="headings", height=6)
        for column, heading in zip(columns, headings):
            tree.heading(column, text=heading)
            tree.column(column, width=130, anchor="center")
        tree.pack(fill="both", expand=True)
        return tree

    def run(self) -> None:
        """Запускает event loop. Блокируется до закрытия окна."""
        self._pump()
        self._redraw()
        self._root.mainloop()

    def _pump(self) -> None:
        if self._closed:
            return
        try:
            for _ in range(self._display_config.max_blocks_per_pump_tick):
                block = self._reader.get_block(timeout=0)
                for frame in self._processor.process(block):
                    self._total_frames += 1
                    if self._frequencies_hz is None:
                        self._frequencies_hz = frame.frequencies_hz
                        self._spectrum_autoscale_mask = _dc_notch_mask(
                            frame.frequencies_hz.shape[0], self._dc_notch_bins
                        )
                    self._spectrum_accumulator.update(frame.power_db)
                    self._estimator.update(frame)
                    if not self._estimator.is_ready:
                        continue
                    for signal in self._detector.update(frame, self._estimator.noise_floor_db()):
                        was_recorded = self._recording_manager.on_signal_finalized(signal)
                        if was_recorded:
                            self._history.appendleft(signal)
                    self._recording_manager.on_active_signals(self._detector.active_signals())
                self._recording_manager.process_block(block)
        except queue.Empty:
            pass

        self._root.after(
            round(self._display_config.queue_pump_interval_s * 1000), self._pump
        )

    def _redraw(self) -> None:
        if self._closed:
            return
        self._redraw_spectrum()
        self._redraw_active_table()
        self._redraw_history_table()
        self._redraw_status()
        self._root.after(round(self._display_config.refresh_interval_s * 1000), self._redraw)

    def _redraw_spectrum(self) -> None:
        power_db = self._spectrum_accumulator.consume()
        if power_db is None or self._frequencies_hz is None:
            return

        freq_mhz = self._frequencies_hz / 1e6
        self._spectrum_power_line.set_data(freq_mhz, power_db)
        visible_values = [power_db[self._spectrum_autoscale_mask]]

        if self._estimator.is_ready:
            noise_floor_db = self._estimator.noise_floor_db()
            open_threshold_db = noise_floor_db + self._detection_config.open_threshold_db
            close_threshold_db = noise_floor_db + self._detection_config.close_threshold_db
            self._spectrum_noise_line.set_data(freq_mhz, noise_floor_db)
            self._spectrum_open_line.set_data(freq_mhz, open_threshold_db)
            self._spectrum_close_line.set_data(freq_mhz, close_threshold_db)
            visible_values.append(noise_floor_db[self._spectrum_autoscale_mask])
            visible_values.append(open_threshold_db[self._spectrum_autoscale_mask])

        self._spectrum_axes.set_xlim(freq_mhz[0], freq_mhz[-1])
        self._spectrum_axes.set_ylim(
            _y_limits_with_margin(
                np.concatenate(visible_values), self._display_config.spectrum_y_margin_db
            )
        )
        self._spectrum_canvas.draw_idle()

    def _redraw_active_table(self) -> None:
        self._active_tree.delete(*self._active_tree.get_children())
        for signal in self._detector.active_signals():
            self._active_tree.insert("", "end", values=_format_active_row(signal))

    def _redraw_history_table(self) -> None:
        self._history_tree.delete(*self._history_tree.get_children())
        for signal in self._history:
            self._history_tree.insert("", "end", values=_format_history_row(signal))

    def _redraw_status(self) -> None:
        noise_floor_state = "ready" if self._estimator.is_ready else "warming up"
        self._status_var.set(
            f"Frames: {self._total_frames} | "
            f"Blocks received: {self._reader.received_blocks} | "
            f"Blocks dropped: {self._reader.dropped_blocks} | "
            f"Discarded during settling: {self._reader.discarded_settle_blocks} | "
            f"Noise floor: {noise_floor_state}"
        )

    def _on_close(self) -> None:
        self._closed = True
        self._reader.stop()
        for signal in self._detector.flush():
            _logger.info("Transmission finalized on window close: %s", signal)
            self._recording_manager.on_signal_finalized(signal)
        self._recording_manager.close_all()
        self._root.destroy()


class _MaxHoldAccumulator:
    """Поэлементный максимум power_db по кадрам, накопленным между consume().

    Отдельная панель спектра перерисовывается реже (refresh_interval_s), чем
    FFTProcessor отдаёт кадры (каждые fft_size*averaging_count / sample_rate_hz
    секунд) — max-hold гарантирует, что короткий всплеск между двумя
    перерисовками не потеряется, а не просто покажет последний кадр.
    """

    def __init__(self) -> None:
        self._max_power_db: np.ndarray | None = None

    def update(self, power_db: np.ndarray) -> None:
        if self._max_power_db is None:
            self._max_power_db = power_db.copy()
        else:
            np.maximum(self._max_power_db, power_db, out=self._max_power_db)

    def consume(self) -> np.ndarray | None:
        """Возвращает накопленный максимум и сбрасывает накопление."""
        result = self._max_power_db
        self._max_power_db = None
        return result


def _dc_notch_mask(bin_count: int, dc_notch_bins: int) -> np.ndarray:
    """True для бинов, которые FFTProcessor НЕ обнулял как DC-notch.

    Используется, чтобы не давать искусственно занулённым (~-200 дБ) DC-бинам
    растягивать автомасштаб оси Y графика спектра — иначе реальный размах
    сигнала/шума становится неразличим на фоне этого выброса.
    """
    mask = np.ones(bin_count, dtype=bool)
    if dc_notch_bins > 0:
        center = bin_count // 2
        mask[center - dc_notch_bins : center + dc_notch_bins + 1] = False
    return mask


def _y_limits_with_margin(values: np.ndarray, margin_db: float) -> tuple[float, float]:
    return float(np.min(values) - margin_db), float(np.max(values) + margin_db)


def _format_active_row(signal: ActiveSignal) -> tuple[str, ...]:
    return (
        f"{signal.center_frequency_hz / 1e6:.4f}",
        f"{signal.current_level_db:.1f}",
        f"{signal.current_snr_db:.1f}",
        f"{signal.peak_level_db:.1f}",
        f"{signal.peak_snr_db:.1f}",
        f"{signal.elapsed_s:.1f}",
    )


def _format_history_row(signal: DetectedSignal) -> tuple[str, ...]:
    return (
        f"{signal.center_frequency_hz / 1e6:.4f}",
        f"{signal.peak_level_db:.1f}",
        f"{signal.peak_snr_db:.1f}",
        _format_time(signal.start_time_utc),
        _format_time(signal.end_time_utc),
        f"{signal.duration_s:.3f}",
    )


def _format_time(value: datetime) -> str:
    return value.strftime("%H:%M:%S.%f")[:-3]
