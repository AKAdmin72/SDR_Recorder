"""Высокоуровневое управление жизненным циклом устройства RTL-SDR."""

from __future__ import annotations

import ctypes
import logging
import threading
from types import TracebackType
from typing import Callable

import numpy as np

from sdr_monitor.config.rtlsdr_radio_config import RtlSdrRadioConfig
from sdr_monitor.hardware.rtlsdr_bindings import RtlSdrReadAsyncCallback, load_library
from sdr_monitor.hardware.rtlsdr_errors import check_result
from sdr_monitor.hardware.sample_format import SampleFormat

_logger = logging.getLogger(__name__)

_DEVICE_INDEX = 0  # проект работает с одним устройством, выбор индекса не нужен
_GAIN_MODE_AUTO = 0
_GAIN_MODE_MANUAL = 1
_STOP_JOIN_TIMEOUT_S = 5.0


class RtlSdrDevice:
    """Контекстный менеджер вокруг одного устройства RTL-SDR.

    При входе: rtlsdr_open() -> применение RtlSdrRadioConfig. При выходе (в том
    числе после исключения): остановка приёма, rtlsdr_close() — устройство не
    должно оставаться "занятым" в libusb.

    В отличие от HackRF, rtlsdr_read_async() блокирует вызывающий поток до
    rtlsdr_cancel_async() — поэтому start_rx() заводит собственный
    daemon-поток, а не полагается на то, что native-код сам управляет приёмом
    в фоне.
    """

    sample_format = SampleFormat.UINT8

    def __init__(self, radio_config: RtlSdrRadioConfig) -> None:
        self._radio_config = radio_config
        self._library = load_library()
        self._device_handle: ctypes.c_void_p | None = None
        # Ссылка на native callback обязана жить, пока идёт приём: если ctypes
        # объект будет собран GC, native-код будет вызывать освобождённую память.
        self._active_callback: RtlSdrReadAsyncCallback | None = None
        self._read_thread: threading.Thread | None = None
        self._is_streaming = False

    def __enter__(self) -> RtlSdrDevice:
        self._open_and_configure()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def _open_and_configure(self) -> None:
        device_ptr = ctypes.c_void_p()
        check_result(
            "rtlsdr_open", self._library.rtlsdr_open(ctypes.byref(device_ptr), _DEVICE_INDEX)
        )
        self._device_handle = device_ptr
        _logger.info("RTL-SDR device opened")

        radio = self._radio_config
        check_result(
            "rtlsdr_set_sample_rate",
            self._library.rtlsdr_set_sample_rate(self._device_handle, radio.sample_rate_hz),
        )
        check_result(
            "rtlsdr_set_center_freq",
            self._library.rtlsdr_set_center_freq(self._device_handle, radio.center_frequency_hz),
        )
        if radio.freq_correction_ppm != 0:
            # librtlsdr возвращает код ошибки -2, если запрошенное значение
            # совпадает с уже установленным (защита от лишней перекалибровки
            # PLL) — при freq_correction_ppm=0 сразу после открытия текущее
            # значение и так уже 0, поэтому вызов пропускается целиком.
            check_result(
                "rtlsdr_set_freq_correction",
                self._library.rtlsdr_set_freq_correction(
                    self._device_handle, radio.freq_correction_ppm
                ),
            )

        if radio.agc_enabled:
            check_result(
                "rtlsdr_set_tuner_gain_mode",
                self._library.rtlsdr_set_tuner_gain_mode(self._device_handle, _GAIN_MODE_AUTO),
            )
            applied_gain_db = None
        else:
            check_result(
                "rtlsdr_set_tuner_gain_mode",
                self._library.rtlsdr_set_tuner_gain_mode(self._device_handle, _GAIN_MODE_MANUAL),
            )
            applied_gain_db = self._apply_nearest_gain(radio.gain_db)

        check_result("rtlsdr_reset_buffer", self._library.rtlsdr_reset_buffer(self._device_handle))

        _logger.info(
            "RTL-SDR configured: freq=%.3f MHz, sample_rate=%.3f Msps, agc=%s, gain=%s, "
            "freq_correction=%d ppm",
            radio.center_frequency_hz / 1e6,
            radio.sample_rate_hz / 1e6,
            radio.agc_enabled,
            "auto" if applied_gain_db is None else f"{applied_gain_db:.1f} dB",
            radio.freq_correction_ppm,
        )

    def _apply_nearest_gain(self, requested_gain_db: float) -> float:
        """Подбирает ближайшее к запрошенному значение усиления из реально
        поддерживаемых конкретным тюнером (список известен только с реального
        устройства, не заранее из конфига) и применяет его."""
        count = self._library.rtlsdr_get_tuner_gains(self._device_handle, None)
        available_tenths_db: list[int] = []
        if count > 0:
            gains_buf = (ctypes.c_int * count)()
            self._library.rtlsdr_get_tuner_gains(self._device_handle, gains_buf)
            available_tenths_db = list(gains_buf)

        requested_tenths_db = round(requested_gain_db * 10)
        if available_tenths_db:
            applied_tenths_db = min(
                available_tenths_db, key=lambda g: abs(g - requested_tenths_db)
            )
        else:
            applied_tenths_db = requested_tenths_db

        check_result(
            "rtlsdr_set_tuner_gain",
            self._library.rtlsdr_set_tuner_gain(self._device_handle, applied_tenths_db),
        )
        if applied_tenths_db != requested_tenths_db:
            _logger.warning(
                "Requested gain %.1f dB is not supported by the tuner, applying "
                "nearest %.1f dB",
                requested_gain_db,
                applied_tenths_db / 10.0,
            )
        return applied_tenths_db / 10.0

    def start_rx(self, callback: Callable[[np.ndarray], None]) -> None:
        """Запускает приём; callback получает сырые межканальные I/Q-байты (uint8)."""
        if self._device_handle is None:
            raise RuntimeError(
                "Device is not open — use RtlSdrDevice as a context manager"
            )
        self._active_callback = RtlSdrReadAsyncCallback(self._make_native_callback(callback))
        self._is_streaming = True
        self._read_thread = threading.Thread(
            target=self._run_read_async, name="RtlSdrReadAsync", daemon=True
        )
        self._read_thread.start()
        _logger.info("IQ reception started")

    def _run_read_async(self) -> None:
        try:
            radio = self._radio_config
            code = self._library.rtlsdr_read_async(
                self._device_handle,
                self._active_callback,
                None,
                radio.read_async_buffer_count,
                radio.read_async_buffer_length,
            )
            if code != 0:
                _logger.warning("rtlsdr_read_async finished with code %d", code)
        except Exception:
            _logger.exception("rtlsdr_read_async finished with an unhandled error")
        finally:
            self._is_streaming = False

    @staticmethod
    def _make_native_callback(
        callback: Callable[[np.ndarray], None],
    ) -> Callable[[ctypes._Pointer, int, ctypes.c_void_p], None]:
        def _on_samples(buf_ptr: ctypes._Pointer, length: int, _ctx: ctypes.c_void_p) -> None:
            try:
                if length <= 0:
                    return
                raw = np.ctypeslib.as_array(buf_ptr, shape=(length,))
                callback(raw)
            except Exception:
                _logger.exception("Unhandled error in RX callback")

        return _on_samples

    def stop_rx(self) -> None:
        if self._device_handle is None or not self._is_streaming:
            return
        check_result("rtlsdr_cancel_async", self._library.rtlsdr_cancel_async(self._device_handle))
        self._join_read_thread()
        _logger.info("IQ reception stopped")

    def _join_read_thread(self) -> None:
        if self._read_thread is not None:
            self._read_thread.join(timeout=_STOP_JOIN_TIMEOUT_S)
            if self._read_thread.is_alive():
                _logger.warning("rtlsdr_read_async thread did not finish within the allotted time")
            self._read_thread = None

    def is_streaming(self) -> bool:
        return self._is_streaming

    def close(self) -> None:
        """Best-effort освобождение ресурсов. Не бросает исключений."""
        if self._device_handle is not None:
            if self._is_streaming:
                self._safe_call("rtlsdr_cancel_async", self._library.rtlsdr_cancel_async)
                self._join_read_thread()
            self._safe_call("rtlsdr_close", self._library.rtlsdr_close)
            self._device_handle = None
            _logger.info("RTL-SDR device closed")
        self._active_callback = None

    def _safe_call(self, operation: str, func: Callable[[ctypes.c_void_p], int]) -> None:
        code = func(self._device_handle)
        if code != 0:
            _logger.warning("%s returned error code %d", operation, code)
