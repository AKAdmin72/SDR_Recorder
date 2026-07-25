"""Коды ошибок librtlsdr и их отображение в исключения Python."""

from __future__ import annotations


class RtlSdrError(RuntimeError):
    """Ошибка вызова librtlsdr.

    В отличие от libhackrf, librtlsdr не предоставляет функцию перевода кода
    ошибки в человекочитаемое имя — сообщение строится только из кода.
    """

    def __init__(self, operation: str, code: int) -> None:
        self.operation = operation
        self.code = code
        super().__init__(f"{operation} failed with error code [{code}]")


def check_result(operation: str, code: int) -> None:
    """Проверяет код возврата функции librtlsdr, бросает RtlSdrError при неудаче.

    0 — единственный код, который не является ошибкой.
    """
    if code != 0:
        raise RtlSdrError(operation, code)
