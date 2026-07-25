"""Сырые ctypes-сигнатуры librtlsdr.dll.

Единственный модуль, который знает о бинарном ABI библиотеки. Не содержит
никакой прикладной логики — только объявления типов callback-ов и
argtypes/restype для функций, используемых RtlSdrDevice. Зеркало
hardware/hackrf_bindings.py по структуре и стилю.

Сигнатуры соответствуют librtlsdr (osmocom), API стабилен с версии 0.5+.
"""

from __future__ import annotations

import ctypes
import os
from pathlib import Path

_DLL_ENV_VAR = "RTLSDR_DLL_PATH"
_DEFAULT_WINDOWS_DLL_PATH = Path(r"C:\RTLSDR\bin\rtlsdr.dll")


RtlSdrReadAsyncCallback = ctypes.CFUNCTYPE(
    None, ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint32, ctypes.c_void_p
)


def _resolve_dll_path() -> str:
    """Определяет путь к rtlsdr.dll: переменная окружения -> известный путь установки."""
    return os.environ.get(_DLL_ENV_VAR, str(_DEFAULT_WINDOWS_DLL_PATH))


def load_library() -> ctypes.CDLL:
    """Загружает rtlsdr.dll и настраивает сигнатуры нужных функций."""
    dll_path = _resolve_dll_path()
    dll_directory = str(Path(dll_path).parent)
    if hasattr(os, "add_dll_directory"):
        # rtlsdr.dll зависит от libusb-1.0.dll/libwinpthread-1.dll, лежащих
        # рядом с ней — как и libhackrf.dll, не подхватываются автоматически.
        os.add_dll_directory(dll_directory)
    try:
        library = ctypes.CDLL(dll_path)
    except OSError as exc:
        raise OSError(
            f"Failed to load rtlsdr.dll from path '{dll_path}'. "
            f"Specify the correct path via the {_DLL_ENV_VAR} environment variable."
        ) from exc

    library.rtlsdr_open.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_uint32]
    library.rtlsdr_open.restype = ctypes.c_int

    library.rtlsdr_close.argtypes = [ctypes.c_void_p]
    library.rtlsdr_close.restype = ctypes.c_int

    library.rtlsdr_set_center_freq.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    library.rtlsdr_set_center_freq.restype = ctypes.c_int

    library.rtlsdr_set_sample_rate.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    library.rtlsdr_set_sample_rate.restype = ctypes.c_int

    library.rtlsdr_set_freq_correction.argtypes = [ctypes.c_void_p, ctypes.c_int]
    library.rtlsdr_set_freq_correction.restype = ctypes.c_int

    library.rtlsdr_set_tuner_gain_mode.argtypes = [ctypes.c_void_p, ctypes.c_int]
    library.rtlsdr_set_tuner_gain_mode.restype = ctypes.c_int

    library.rtlsdr_set_tuner_gain.argtypes = [ctypes.c_void_p, ctypes.c_int]
    library.rtlsdr_set_tuner_gain.restype = ctypes.c_int

    library.rtlsdr_get_tuner_gains.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
    library.rtlsdr_get_tuner_gains.restype = ctypes.c_int

    library.rtlsdr_reset_buffer.argtypes = [ctypes.c_void_p]
    library.rtlsdr_reset_buffer.restype = ctypes.c_int

    library.rtlsdr_read_async.argtypes = [
        ctypes.c_void_p,
        RtlSdrReadAsyncCallback,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
    ]
    library.rtlsdr_read_async.restype = ctypes.c_int

    library.rtlsdr_cancel_async.argtypes = [ctypes.c_void_p]
    library.rtlsdr_cancel_async.restype = ctypes.c_int

    return library
