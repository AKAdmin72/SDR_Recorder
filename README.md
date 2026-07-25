# SDR Monitor

Real-time monitoring, detection, and recording of radio transmissions from a
HackRF or RTL-SDR receiver. Watches a chosen frequency band, detects
transmissions against an adaptive noise floor, demodulates them (AM or FM),
and saves each one as a WAV file — with a live spectrum/activity GUI or a
headless mode for unattended recording.

[Читать на русском / Russian version](README_RUS.md)

## Features

- **Live spectrum view**: max-hold spectrum plot, noise floor, open/close
  detection thresholds, and blacklisted (excluded) frequency ranges, all
  overlaid on one graph.
- **Automatic detection**: per-bin adaptive noise floor (rolling percentile)
  with hysteresis (separate open/close thresholds) and multi-frame
  confirmation to reject transient noise spikes.
- **AM and FM demodulation**, selected per config profile.
- **Automatic WAV recording** of each detected transmission, with a minimum
  duration filter and post-roll so short noise blips don't produce junk files
  and real transmissions aren't clipped.
- **Multiple named config profiles** (`config/*.toml`) — e.g. one per
  band/device/modulation combination — with an interactive picker at startup
  when more than one is present.
- **GUI config editor** (`sdr-monitor-config`, or the "Config..." button in
  the main window) — a structured form over every config field, including
  full add/remove editing of blacklisted frequency ranges. Edits are applied
  as targeted text patches to the TOML file, so existing comments and
  formatting are preserved.
- **HackRF and RTL-SDR** support through a common device interface.

## Architecture

One streaming pipeline, shared by both GUI and headless mode:

```
SDR (HackRF / RTL-SDR)
  -> IQStreamReader        (async USB capture, queued IQ blocks)
  -> FFTProcessor           (windowed FFT, averaging, DC-notch)
  -> NoiseFloorEstimator    (rolling per-bin percentile)
  -> SignalDetector         (hysteresis + multi-frame confirmation -> tracks)
  -> RecordingManager
       -> ChannelExtractor  (mix-to-baseband + decimate to the detected channel)
       -> Demodulator       (AM envelope or FM quadrature discriminator)
       -> AudioFilter       (voice-band bandpass)
       -> AudioResampler    (decimate to the output WAV sample rate)
       -> WaveRecorder      (buffered in memory, written to disk once the
                              minimum duration is reached)
```

The GUI and headless entry points (`run_gui` / `run_headless` in `app.py`)
build the exact same pipeline; the GUI additionally drives a `tkinter`
window (`MonitorWindow`) that polls the queue on a timer instead of a
background thread, since Tcl/Tk requires single-threaded access.

## Requirements

- Python >= 3.11
- A HackRF One or RTL-SDR (RTL2832U-based) receiver
- The vendor's native driver library:
  - HackRF: `libhackrf.dll` (default expected at `C:\HackRF\bin\libhackrf.dll`,
    override with the `HACKRF_DLL_PATH` environment variable)
  - RTL-SDR: `rtlsdr.dll` (default expected at `C:\RTLSDR\bin\rtlsdr.dll`,
    override with the `RTLSDR_DLL_PATH` environment variable)

  Both are loaded directly via `ctypes` — no `pyhackrf`/`pyrtlsdr` Python
  package is required, just the native DLL (and its own dependencies,
  `libusb-1.0.dll`/`libwinpthread-1.dll`, alongside it).

## Installation

```
pip install -e .
```

This installs the `sdr-monitor` and `sdr-monitor-config` console scripts
(see `pyproject.toml`).

For running the test suite:

```
pip install -e ".[dev]"
```

## Usage

Run with a config profile picked interactively (if `config/` holds more than
one `*.toml` file) or explicitly:

```
sdr-monitor
sdr-monitor --config config/rtl_126_3_am.toml
```

Headless mode (no GUI — for unattended/background recording):

```
sdr-monitor --headless
sdr-monitor --headless --duration 3600   # stop automatically after 1 hour
```

Config editor (standalone GUI, or click "Config..." in the main window):

```
sdr-monitor-config
sdr-monitor-config --config config/app_config.toml
```

## Configuration

Every runtime parameter — device selection, tuning, gain, FFT size,
detection thresholds, demodulation mode, recording behavior — lives in a
TOML file under `config/`. `config/app_config.toml` is the default; other
files are named profiles for specific bands/devices/modes, e.g.:

- `config/rtl_126_3_am.toml` — RTL-SDR, 126.3 MHz, AM (aviation band)
- `config/rtl_155_1_fm.toml` — RTL-SDR, 155.1 MHz, FM
- `config/hackrf_126_3_am.toml` — HackRF, 126.3 MHz, AM (aviation band)
- `config/hackrf_155_1_fm.toml` — HackRF, 155.1 MHz, FM

Both `[radio.hackrf]` and `[radio.rtlsdr]` sections may be present in the
same file; only the one matching `[sdr].type` is actually used, so switching
receivers doesn't require deleting the other section. Frequency ranges that
should be excluded from detection entirely (e.g. a receiver's own spurious
artifacts) go under `[[detection.blacklisted_ranges]]`.

Every field in the config files is commented with its meaning, valid range,
and — where relevant — the reasoning behind the current value.

## Testing

```
pytest
```

The test suite is fully self-contained (no hardware required) — hardware
device classes are exercised through a common `SdrDevice` interface and
factory, allowing the rest of the pipeline to be tested with synthetic IQ
data.

## Recordings

Detected transmissions are saved as WAV files under `recordings/` (path
configurable via `audio.recordings_dir`), one file per transmission, named
with a UTC timestamp and center frequency.
