"""GUI-редактор config/app_config.toml — структурированная форма на каждое поле.

Правка идёт точечно поверх исходного текста файла (см.
`sdr_monitor.config.toml_writer.update_scalar`), поэтому все пояснительные
комментарии в TOML при сохранении остаются на месте. Перед записью на диск
изменённый текст валидируется через
`sdr_monitor.config.config_loader.load_config_from_text` — невалидный конфиг
никогда не попадает в файл.

Секции `[radio.hackrf]`/`[radio.rtlsdr]` в файле присутствуют всегда, но
реально использует конвейер только ту, что совпадает с `[sdr].type` — форма
показывает исключительно активную секцию и переключает её при смене типа
SDR, чтобы нельзя было (как уже случалось) отредактировать не ту секцию.

Два способа запуска, один и тот же класс `ConfigEditorFrame`:
  - `python -m sdr_monitor.config_editor [--config путь]` — отдельное окно.
  - Кнопка "Config..." в `MonitorWindow` — то же самое как Toplevel.
"""

from __future__ import annotations

import argparse
import tomllib
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from sdr_monitor.config.config_loader import load_config_from_text
from sdr_monitor.config.toml_writer import replace_array_of_tables, update_scalar
from sdr_monitor.config_selector import select_config_path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CONFIG_DIR = _PROJECT_ROOT / "config"


@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: str
    kind: str  # "int" | "float" | "bool" | "str" | "combobox" | "path"
    unit: str | None = None
    choices: tuple[str, ...] | None = None


@dataclass(frozen=True)
class SectionSpec:
    title: str
    toml_section: str
    fields: tuple[FieldSpec, ...]


_FORM_SCHEMA: tuple[SectionSpec, ...] = (
    SectionSpec(
        "SDR",
        "sdr",
        (FieldSpec("type", "Receiver type", "combobox", choices=("hackrf", "rtlsdr")),),
    ),
    SectionSpec(
        "Radio (HackRF)",
        "radio.hackrf",
        (
            FieldSpec("center_frequency_hz", "Tuning frequency", "int", unit="Hz"),
            FieldSpec("sample_rate_hz", "Sample rate", "int", unit="Hz"),
            FieldSpec("lna_gain_db", "LNA gain", "int", unit="dB"),
            FieldSpec("vga_gain_db", "VGA gain", "int", unit="dB"),
            FieldSpec("amp_enable", "Built-in amplifier (+14dB)", "bool"),
            FieldSpec("settle_time_s", "Settle time", "float", unit="s"),
        ),
    ),
    SectionSpec(
        "Radio (RTL-SDR)",
        "radio.rtlsdr",
        (
            FieldSpec("center_frequency_hz", "Tuning frequency", "int", unit="Hz"),
            FieldSpec("sample_rate_hz", "Sample rate", "int", unit="Hz"),
            FieldSpec("gain_db", "Tuner gain", "float", unit="dB"),
            FieldSpec("agc_enabled", "Automatic gain control", "bool"),
            FieldSpec("freq_correction_ppm", "Frequency correction", "int", unit="ppm"),
            FieldSpec("settle_time_s", "Settle time", "float", unit="s"),
            FieldSpec("read_async_buffer_count", "Number of receive buffers", "int"),
            FieldSpec("read_async_buffer_length", "Receive buffer size", "int", unit="bytes"),
        ),
    ),
    SectionSpec(
        "FFT",
        "fft",
        (
            FieldSpec("fft_size", "FFT size", "int"),
            FieldSpec(
                "window_type",
                "Window function",
                "combobox",
                choices=("hann", "hamming", "blackmanharris", "rectangular"),
            ),
            FieldSpec("averaging_count", "Frame averaging", "int"),
            FieldSpec("dc_notch_bins", "DC notch, bins", "int"),
        ),
    ),
    SectionSpec(
        "Noise floor",
        "noise_floor",
        (
            FieldSpec("window_seconds", "Estimation window", "float", unit="s"),
            FieldSpec("update_interval_s", "Update interval", "float", unit="s"),
            FieldSpec("percentile", "Percentile", "float", unit="%"),
            FieldSpec("warmup_seconds", "Warm-up", "float", unit="s"),
        ),
    ),
    SectionSpec(
        "Detection",
        "detection",
        (
            FieldSpec("open_threshold_db", "Open threshold", "float", unit="dB"),
            FieldSpec("close_threshold_db", "Close threshold", "float", unit="dB"),
            FieldSpec("min_bandwidth_bins", "Min. bandwidth", "int", unit="bins"),
            FieldSpec("open_confirm_frames", "Frames to confirm open", "int"),
            FieldSpec("close_confirm_frames", "Frames to confirm close", "int"),
            FieldSpec(
                "frequency_match_tolerance_hz", "Frequency match tolerance", "float", unit="Hz"
            ),
        ),
    ),
    SectionSpec(
        "Display",
        "display",
        (
            FieldSpec("refresh_interval_s", "Redraw interval", "float", unit="s"),
            FieldSpec("queue_pump_interval_s", "Queue pump interval", "float", unit="s"),
            FieldSpec("history_size", "History size", "int"),
            FieldSpec("spectrum_y_margin_db", "Y-axis margin", "float", unit="dB"),
        ),
    ),
    SectionSpec(
        "Audio",
        "audio",
        (
            FieldSpec("channel_half_bandwidth_hz", "Channel half-bandwidth", "float", unit="Hz"),
            FieldSpec("channel_intermediate_sample_rate_hz", "Intermediate sample rate", "int", unit="Hz"),
            FieldSpec("channel_filter_taps", "Channel LPF taps", "int"),
            FieldSpec("modulation_type", "Demodulation", "combobox", choices=("am", "fm")),
            FieldSpec("fm_deviation_hz", "FM deviation", "float", unit="Hz"),
            FieldSpec("voice_band_low_hz", "Voice band, low", "float", unit="Hz"),
            FieldSpec("voice_band_high_hz", "Voice band, high", "float", unit="Hz"),
            FieldSpec("voice_filter_order", "Voice filter order", "int"),
            FieldSpec("audio_sample_rate_hz", "WAV sample rate", "int", unit="Hz"),
            FieldSpec("audio_resample_cutoff_hz", "Resampler LPF cutoff", "float", unit="Hz"),
            FieldSpec("audio_resample_filter_taps", "Resampler LPF taps", "int"),
            FieldSpec("am_pcm_full_scale_input", "PCM full scale (AM)", "float"),
            FieldSpec("fm_pcm_full_scale_input", "PCM full scale (FM)", "float"),
            FieldSpec("recordings_dir", "Recordings directory", "path"),
            FieldSpec("min_recording_duration_s", "Min. recording duration", "float", unit="s"),
            FieldSpec("post_roll_duration_s", "Post-roll", "float", unit="s"),
        ),
    ),
    SectionSpec(
        "Acquisition",
        "acquisition",
        (
            FieldSpec("queue_max_blocks", "Max blocks in queue", "int"),
            FieldSpec("stats_log_interval_s", "Stats log interval", "float", unit="s"),
        ),
    ),
    SectionSpec(
        "Logging",
        "logging",
        (
            FieldSpec(
                "level", "Level", "combobox",
                choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
            ),
        ),
    ),
)


def _get_raw_section(raw: dict, toml_section: str) -> dict:
    node = raw
    for part in toml_section.split("."):
        node = node[part]
    return node


class ConfigEditorFrame(ttk.Frame):
    """Форма редактирования всех скалярных полей AppConfig поверх TOML-файла."""

    def __init__(self, parent: tk.Misc, config_path: Path) -> None:
        super().__init__(parent)
        self._config_path = config_path
        self._text = ""
        self._vars: dict[tuple[str, str], tk.Variable] = {}
        self._field_specs: dict[tuple[str, str], FieldSpec] = {}
        self._section_frames: dict[str, ttk.Frame] = {}
        self._sdr_type_var: tk.StringVar | None = None
        self._blacklist_rows_frame: ttk.Frame | None = None
        self._blacklist_rows: list[dict] = []

        self._build_widgets()
        try:
            self._load(config_path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Config load error", str(exc))

    def _build_widgets(self) -> None:
        button_row = ttk.Frame(self)
        button_row.pack(side="bottom", fill="x", padx=8, pady=8)
        ttk.Button(button_row, text="Save", command=self._on_save).pack(
            side="left", padx=(0, 4)
        )
        ttk.Button(button_row, text="Reload from disk", command=self._on_reload).pack(side="left")
        self._status_var = tk.StringVar()
        ttk.Label(button_row, textvariable=self._status_var).pack(side="left", padx=8)

        canvas_frame = ttk.Frame(self)
        canvas_frame.pack(side="top", fill="both", expand=True)
        canvas = tk.Canvas(canvas_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        inner = ttk.Frame(canvas)
        inner.bind(
            "<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=inner, anchor="nw")

        radio_container: ttk.Frame | None = None
        for spec in _FORM_SCHEMA:
            if spec.toml_section.startswith("radio."):
                if radio_container is None:
                    radio_container = ttk.Frame(inner)
                    radio_container.pack(fill="x")
                parent_for_section = radio_container
            else:
                parent_for_section = inner
            self._build_section(spec, parent_for_section)

    def _build_section(self, spec: SectionSpec, parent: ttk.Frame) -> None:
        outer = ttk.Frame(parent)
        outer.pack(fill="x", padx=8, pady=4)
        self._section_frames[spec.toml_section] = outer

        body = ttk.Frame(outer)
        is_open = tk.BooleanVar(value=True)

        def toggle() -> None:
            if is_open.get():
                body.pack_forget()
                is_open.set(False)
                toggle_btn.configure(text=f"▶ {spec.title}")
            else:
                body.pack(fill="x", padx=(16, 0), pady=(4, 0))
                is_open.set(True)
                toggle_btn.configure(text=f"▾ {spec.title}")

        toggle_btn = ttk.Button(outer, text=f"▾ {spec.title}", command=toggle)
        toggle_btn.pack(fill="x")
        body.pack(fill="x", padx=(16, 0), pady=(4, 0))

        for row, field in enumerate(spec.fields):
            self._build_field_row(body, spec.toml_section, field, row)

        if spec.toml_section == "detection":
            self._build_blacklist_editor(body, len(spec.fields))

    def _build_blacklist_editor(self, parent: ttk.Frame, grid_row: int) -> None:
        # Отдельный контейнер под pack() внутри ячейки grid — на одном
        # родителе нельзя смешивать grid и pack, а список диапазонов
        # переменной длины (добавление/удаление строк) на pack() удобнее.
        container = ttk.Frame(parent)
        container.grid(row=grid_row, column=0, columnspan=4, sticky="ew", pady=(8, 0))

        ttk.Label(container, text="Blacklisted ranges (frequency exclusions):").pack(anchor="w")
        self._blacklist_rows_frame = ttk.Frame(container)
        self._blacklist_rows_frame.pack(fill="x", pady=(2, 2))
        ttk.Button(
            container, text="+ Add range", command=lambda: self._add_blacklist_row()
        ).pack(anchor="w")

    def _add_blacklist_row(self, start_hz: object = None, end_hz: object = None) -> None:
        row_frame = ttk.Frame(self._blacklist_rows_frame)
        row_frame.pack(fill="x", pady=1)

        start_var = tk.StringVar(value="" if start_hz is None else str(start_hz))
        end_var = tk.StringVar(value="" if end_hz is None else str(end_hz))

        ttk.Entry(row_frame, textvariable=start_var, width=14).pack(side="left")
        ttk.Label(row_frame, text=" - ").pack(side="left")
        ttk.Entry(row_frame, textvariable=end_var, width=14).pack(side="left")
        ttk.Label(row_frame, text=" Hz", foreground="gray").pack(side="left", padx=(0, 8))

        row_entry = {"frame": row_frame, "start_var": start_var, "end_var": end_var}
        ttk.Button(
            row_frame, text="✕", width=3, command=lambda: self._remove_blacklist_row(row_entry)
        ).pack(side="left")

        self._blacklist_rows.append(row_entry)

    def _remove_blacklist_row(self, row_entry: dict) -> None:
        row_entry["frame"].destroy()
        self._blacklist_rows.remove(row_entry)

    def _build_field_row(
        self, parent: ttk.Frame, toml_section: str, field: FieldSpec, row: int
    ) -> None:
        ttk.Label(parent, text=field.label).grid(row=row, column=0, sticky="w", pady=1, padx=(0, 8))

        if field.kind == "bool":
            var: tk.Variable = tk.BooleanVar()
            widget = ttk.Checkbutton(parent, variable=var)
        elif field.kind == "combobox":
            var = tk.StringVar()
            widget = ttk.Combobox(
                parent, textvariable=var, values=field.choices, state="readonly", width=15
            )
        elif field.kind == "path":
            var = tk.StringVar()
            widget = ttk.Entry(parent, textvariable=var, width=32)
        else:
            var = tk.StringVar()
            widget = ttk.Entry(parent, textvariable=var, width=18)
        widget.grid(row=row, column=1, sticky="w", pady=1)

        if field.unit:
            ttk.Label(parent, text=field.unit, foreground="gray").grid(
                row=row, column=2, sticky="w", padx=(4, 0)
            )
        if field.kind == "path":
            ttk.Button(
                parent, text="Browse...", command=lambda v=var: self._browse_directory(v)
            ).grid(row=row, column=3, padx=(4, 0))

        self._vars[(toml_section, field.name)] = var
        self._field_specs[(toml_section, field.name)] = field

        if toml_section == "sdr" and field.name == "type":
            self._sdr_type_var = var
            var.trace_add("write", lambda *_a: self._update_radio_visibility())

    def _browse_directory(self, var: tk.StringVar) -> None:
        chosen = filedialog.askdirectory(initialdir=var.get() or str(_PROJECT_ROOT))
        if chosen:
            var.set(chosen)

    def _update_radio_visibility(self) -> None:
        if self._sdr_type_var is None:
            return
        active = self._sdr_type_var.get()
        for sdr_type in ("hackrf", "rtlsdr"):
            frame = self._section_frames.get(f"radio.{sdr_type}")
            if frame is None:
                continue
            if sdr_type == active:
                frame.pack(fill="x", padx=8, pady=4)
            else:
                frame.pack_forget()

    def _load(self, config_path: Path) -> None:
        text = config_path.read_text(encoding="utf-8")
        raw = tomllib.loads(text)  # синтаксическая проверка сразу; полная — через load_config_from_text

        for (toml_section, key), var in self._vars.items():
            section_dict = _get_raw_section(raw, toml_section)
            if key not in section_dict:
                continue
            value = section_dict[key]
            if isinstance(var, tk.BooleanVar):
                var.set(bool(value))
            else:
                var.set(str(value))

        for row_entry in list(self._blacklist_rows):
            self._remove_blacklist_row(row_entry)
        detection_raw = _get_raw_section(raw, "detection")
        for entry in detection_raw.get("blacklisted_ranges", []):
            self._add_blacklist_row(entry.get("start_hz"), entry.get("end_hz"))

        self._config_path = config_path
        self._text = text
        self._update_radio_visibility()
        self._status_var.set(f"Loaded: {config_path}")

    def _coerce_value(self, toml_section: str, key: str, var: tk.Variable) -> bool | int | float | str:
        field = self._field_specs[(toml_section, key)]
        if field.kind == "bool":
            return bool(var.get())

        raw_value = var.get().strip()
        if field.kind == "int":
            try:
                return int(raw_value)
            except ValueError:
                raise ValueError(f"{field.label}: {raw_value!r} — must be an integer") from None
        if field.kind == "float":
            try:
                return float(raw_value)
            except ValueError:
                raise ValueError(f"{field.label}: {raw_value!r} — must be a number") from None
        return raw_value

    def _collect_blacklist_entries(self) -> list[dict[str, int]]:
        entries = []
        for row_entry in self._blacklist_rows:
            start_raw = row_entry["start_var"].get().strip()
            end_raw = row_entry["end_var"].get().strip()
            try:
                start_hz = int(start_raw)
                end_hz = int(end_raw)
            except ValueError:
                raise ValueError(
                    f"Blacklisted range: values must be integers "
                    f"(got {start_raw!r}, {end_raw!r})"
                ) from None
            entries.append({"start_hz": start_hz, "end_hz": end_hz})
        return entries

    def _on_save(self) -> None:
        try:
            new_text = self._text
            for (toml_section, key), var in self._vars.items():
                value = self._coerce_value(toml_section, key, var)
                new_text = update_scalar(new_text, toml_section, key, value)
            new_text = replace_array_of_tables(
                new_text, "detection.blacklisted_ranges", self._collect_blacklist_entries()
            )
            load_config_from_text(new_text, str(self._config_path))
        except ValueError as exc:
            messagebox.showerror("Validation error", str(exc))
            return

        self._config_path.write_text(new_text, encoding="utf-8")
        self._text = new_text
        self._status_var.set(f"Saved: {self._config_path}")
        messagebox.showinfo(
            "Saved",
            "Config saved. Changes take effect on the next application "
            "start — hot reload is not supported.",
        )

    def _on_reload(self) -> None:
        try:
            self._load(self._config_path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Config load error", str(exc))


def open_as_toplevel(parent: tk.Misc, config_path: Path) -> tk.Toplevel:
    """Открывает редактор как дочернее окно уже запущенного приложения (кнопка Config)."""
    window = tk.Toplevel(parent)
    window.title(f"Config — {config_path.name}")
    editor = ConfigEditorFrame(window, config_path)
    editor.pack(fill="both", expand=True)
    return window


def run_standalone(config_path: Path) -> None:
    root = tk.Tk()
    root.title(f"SDR Monitor — Config Editor ({config_path.name})")
    editor = ConfigEditorFrame(root, config_path)
    editor.pack(fill="both", expand=True)
    root.mainloop()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Standalone GUI config editor for SDR Monitor")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to the TOML config. If omitted, prompts interactively from "
        "config/ when more than one file is present.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    config_path = select_config_path(_CONFIG_DIR, args.config)
    run_standalone(config_path)


if __name__ == "__main__":
    main()
