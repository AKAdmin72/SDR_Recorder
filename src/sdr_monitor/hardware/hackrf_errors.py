"""Коды ошибок libhackrf и их отображение в исключения Python."""

from __future__ import annotations

import ctypes
import enum


class HackRFErrorCode(enum.IntEnum):
    """Зеркало enum hackrf_error из libhackrf.h."""

    SUCCESS = 0
    TRUE = 1
    INVALID_PARAM = -2
    NOT_FOUND = -5
    BUSY = -6
    NO_MEM = -11
    LIBUSB = -1000
    THREAD = -1001
    STREAMING_THREAD_ERR = -1002
    STREAMING_STOPPED = -1003
    STREAMING_EXIT_CALLED = -1004
    USB_API_VERSION = -1005
    NOT_LAST_DEVICE = -2000
    OTHER = -9999


class HackRFError(RuntimeError):
    """Ошибка вызова libhackrf с человекочитаемым сообщением."""

    def __init__(self, operation: str, code: int, message: str) -> None:
        self.operation = operation
        self.code = code
        super().__init__(f"{operation} failed with error [{code}]: {message}")


def check_result(library: ctypes.CDLL, operation: str, code: int) -> None:
    """Проверяет код возврата функции libhackrf, бросает HackRFError при неудаче.

    HACKRF_SUCCESS (0) — единственный код, который не является ошибкой для
    большинства функций управления устройством.
    """
    if code == HackRFErrorCode.SUCCESS:
        return
    message = library.hackrf_error_name(code).decode("ascii", errors="replace")
    raise HackRFError(operation, code, message)
