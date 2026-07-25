"""Высокоуровневое управление жизненным циклом устройства HackRF."""

from __future__ import annotations

import ctypes
import logging
from types import TracebackType
from typing import Callable

import numpy as np

from sdr_monitor.config.hackrf_radio_config import HackRFRadioConfig
from sdr_monitor.hardware.hackrf_bindings import HackRFSampleBlockCallback, load_library
from sdr_monitor.hardware.hackrf_errors import HackRFErrorCode, check_result
from sdr_monitor.hardware.sample_format import SampleFormat

_logger = logging.getLogger(__name__)


class HackRFDevice:
    """Контекстный менеджер вокруг одного устройства HackRF One.

    При входе: hackrf_init() -> hackrf_open() -> применение HackRFRadioConfig.
    При выходе (в том числе после исключения): остановка приёма, hackrf_close(),
    hackrf_exit() — устройство не должно оставаться "занятым" в libusb.
    """

    sample_format = SampleFormat.INT8

    def __init__(self, radio_config: HackRFRadioConfig) -> None:
        self._radio_config = radio_config
        self._library = load_library()
        self._device_handle: ctypes.c_void_p | None = None
        # Ссылка на native callback обязана жить, пока идёт приём: если ctypes
        # объект будет собран GC, native-код будет вызывать освобождённую память.
        self._active_callback: HackRFSampleBlockCallback | None = None

    def __enter__(self) -> HackRFDevice:
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
        check_result(self._library, "hackrf_init", self._library.hackrf_init())

        device_ptr = ctypes.c_void_p()
        check_result(
            self._library,
            "hackrf_open",
            self._library.hackrf_open(ctypes.byref(device_ptr)),
        )
        self._device_handle = device_ptr
        _logger.info("HackRF device opened")

        radio = self._radio_config
        check_result(
            self._library,
            "hackrf_set_freq",
            self._library.hackrf_set_freq(self._device_handle, radio.center_frequency_hz),
        )
        check_result(
            self._library,
            "hackrf_set_sample_rate",
            self._library.hackrf_set_sample_rate(
                self._device_handle, float(radio.sample_rate_hz)
            ),
        )
        check_result(
            self._library,
            "hackrf_set_lna_gain",
            self._library.hackrf_set_lna_gain(self._device_handle, radio.lna_gain_db),
        )
        check_result(
            self._library,
            "hackrf_set_vga_gain",
            self._library.hackrf_set_vga_gain(self._device_handle, radio.vga_gain_db),
        )
        check_result(
            self._library,
            "hackrf_set_amp_enable",
            self._library.hackrf_set_amp_enable(self._device_handle, int(radio.amp_enable)),
        )
        _logger.info(
            "HackRF configured: freq=%.3f MHz, sample_rate=%.3f Msps, lna=%d dB, "
            "vga=%d dB, amp=%s",
            radio.center_frequency_hz / 1e6,
            radio.sample_rate_hz / 1e6,
            radio.lna_gain_db,
            radio.vga_gain_db,
            radio.amp_enable,
        )

    def start_rx(self, callback: Callable[[np.ndarray], None]) -> None:
        """Запускает приём; callback получает сырые межканальные I/Q-байты (uint8).

        Оборачивает переданный python-callback в native HackRFSampleBlockCallback:
        разворачивает hackrf_transfer (valid_length/buffer) в numpy-массив и
        передаёт его выше — вызывающий код (IQStreamReader) не должен знать
        про ABI libhackrf.
        """
        if self._device_handle is None:
            raise RuntimeError(
                "Device is not open — use HackRFDevice as a context manager"
            )
        self._active_callback = HackRFSampleBlockCallback(self._make_native_callback(callback))
        check_result(
            self._library,
            "hackrf_start_rx",
            self._library.hackrf_start_rx(self._device_handle, self._active_callback, None),
        )
        _logger.info("IQ reception started")

    @staticmethod
    def _make_native_callback(
        callback: Callable[[np.ndarray], None],
    ) -> Callable[[ctypes._Pointer], int]:
        def _on_transfer(transfer_ptr: ctypes._Pointer) -> int:
            try:
                transfer = transfer_ptr.contents
                valid_length = transfer.valid_length
                if valid_length <= 0:
                    return 0
                raw = np.ctypeslib.as_array(transfer.buffer, shape=(valid_length,))
                callback(raw)
                return 0
            except Exception:
                _logger.exception(
                    "Unhandled error in RX callback — reception will stop"
                )
                return 1

        return _on_transfer

    def stop_rx(self) -> None:
        if self._device_handle is None:
            return
        check_result(
            self._library, "hackrf_stop_rx", self._library.hackrf_stop_rx(self._device_handle)
        )
        _logger.info("IQ reception stopped")

    def is_streaming(self) -> bool:
        if self._device_handle is None:
            return False
        return self._library.hackrf_is_streaming(self._device_handle) == HackRFErrorCode.TRUE

    def close(self) -> None:
        """Best-effort освобождение ресурсов. Не бросает исключений."""
        if self._device_handle is not None:
            if self.is_streaming():
                self._safe_call("hackrf_stop_rx", self._library.hackrf_stop_rx)
            self._safe_call("hackrf_close", self._library.hackrf_close)
            self._device_handle = None
            _logger.info("HackRF device closed")
        self._active_callback = None
        self._safe_call("hackrf_exit", self._library.hackrf_exit, use_device_handle=False)

    def _safe_call(self, operation: str, func, *, use_device_handle: bool = True) -> None:
        code = func(self._device_handle) if use_device_handle else func()
        if code != HackRFErrorCode.SUCCESS:
            _logger.warning("%s returned error code %d", operation, code)
