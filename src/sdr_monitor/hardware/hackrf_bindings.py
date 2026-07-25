"""Сырые ctypes-сигнатуры libhackrf.dll.

Единственный модуль, который знает о бинарном ABI библиотеки. Не содержит
никакой прикладной логики — только объявления структур, типов callback-ов
и argtypes/restype для функций, используемых на Этапе 1.

Сигнатуры соответствуют libhackrf версии 2023.01.1 (см. hackrf_info).
"""

from __future__ import annotations

import ctypes
import os
from pathlib import Path

_DLL_ENV_VAR = "HACKRF_DLL_PATH"
_DEFAULT_WINDOWS_DLL_PATH = Path(r"C:\HackRF\bin\libhackrf.dll")


class HackRFTransfer(ctypes.Structure):
    """Зеркало struct hackrf_transfer из libhackrf.h."""

    _fields_ = [
        ("device", ctypes.c_void_p),
        ("buffer", ctypes.POINTER(ctypes.c_ubyte)),
        ("buffer_length", ctypes.c_int),
        ("valid_length", ctypes.c_int),
        ("rx_ctx", ctypes.c_void_p),
        ("tx_ctx", ctypes.c_void_p),
    ]


HackRFSampleBlockCallback = ctypes.CFUNCTYPE(
    ctypes.c_int, ctypes.POINTER(HackRFTransfer)
)


def _resolve_dll_path() -> str:
    """Определяет путь к libhackrf.dll: переменная окружения -> известный путь установки."""
    return os.environ.get(_DLL_ENV_VAR, str(_DEFAULT_WINDOWS_DLL_PATH))


def load_library() -> ctypes.CDLL:
    """Загружает libhackrf.dll и настраивает сигнатуры нужных функций."""
    dll_path = _resolve_dll_path()
    dll_directory = str(Path(dll_path).parent)
    if hasattr(os, "add_dll_directory"):
        # libhackrf.dll зависит от libusb-1.0.dll/libwinpthread-1.dll, лежащих
        # рядом с ней. Начиная с Python 3.8 они не подхватываются автоматически
        # даже при полном пути к самой DLL — нужно явно расширить search path.
        os.add_dll_directory(dll_directory)
    try:
        library = ctypes.CDLL(dll_path)
    except OSError as exc:
        raise OSError(
            f"Failed to load libhackrf.dll from path '{dll_path}'. "
            f"Specify the correct path via the {_DLL_ENV_VAR} environment variable."
        ) from exc

    library.hackrf_init.argtypes = []
    library.hackrf_init.restype = ctypes.c_int

    library.hackrf_exit.argtypes = []
    library.hackrf_exit.restype = ctypes.c_int

    library.hackrf_open.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
    library.hackrf_open.restype = ctypes.c_int

    library.hackrf_close.argtypes = [ctypes.c_void_p]
    library.hackrf_close.restype = ctypes.c_int

    library.hackrf_set_freq.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
    library.hackrf_set_freq.restype = ctypes.c_int

    library.hackrf_set_sample_rate.argtypes = [ctypes.c_void_p, ctypes.c_double]
    library.hackrf_set_sample_rate.restype = ctypes.c_int

    library.hackrf_set_lna_gain.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    library.hackrf_set_lna_gain.restype = ctypes.c_int

    library.hackrf_set_vga_gain.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    library.hackrf_set_vga_gain.restype = ctypes.c_int

    library.hackrf_set_amp_enable.argtypes = [ctypes.c_void_p, ctypes.c_uint8]
    library.hackrf_set_amp_enable.restype = ctypes.c_int

    library.hackrf_start_rx.argtypes = [
        ctypes.c_void_p,
        HackRFSampleBlockCallback,
        ctypes.c_void_p,
    ]
    library.hackrf_start_rx.restype = ctypes.c_int

    library.hackrf_stop_rx.argtypes = [ctypes.c_void_p]
    library.hackrf_stop_rx.restype = ctypes.c_int

    library.hackrf_is_streaming.argtypes = [ctypes.c_void_p]
    library.hackrf_is_streaming.restype = ctypes.c_int

    library.hackrf_error_name.argtypes = [ctypes.c_int]
    library.hackrf_error_name.restype = ctypes.c_char_p

    return library
