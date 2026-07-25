"""Мост между сырыми I/Q-байтами устройства и потребителями IQBlock.

Полностью не знает о конкретном железе (HackRF/RTL-SDR/...) — этим владеет
класс устройства (см. hardware/hackrf_device.py, hardware/rtlsdr_device.py),
который сам разворачивает свой native ABI и передаёт сюда уже готовый
numpy-массив сырых межканальных байт через SdrDevice.start_rx(callback).
"""

from __future__ import annotations

import logging
import queue
from datetime import datetime, timezone

import numpy as np

from sdr_monitor.acquisition.iq_block import IQBlock
from sdr_monitor.config.acquisition_config import AcquisitionConfig
from sdr_monitor.config.radio_config import RadioConfig
from sdr_monitor.hardware.sample_format import SampleFormat
from sdr_monitor.hardware.sdr_device import SdrDevice

_logger = logging.getLogger(__name__)

_INT8_FULL_SCALE = 128.0
_UINT8_MIDPOINT = 127.5
_UINT8_FULL_SCALE = 127.5


def convert_raw_iq_to_complex64(raw: np.ndarray, sample_format: SampleFormat) -> np.ndarray:
    """Конвертирует чередующиеся сырые I/Q-отсчёты в complex64.

    Векторизовано, без Python-циклов. `raw` — 1-D массив байт чётной длины
    (I0,Q0,I1,Q1,...), как их отдаёт устройство. Выделяет новую память под
    результат (не является view на переданный `raw`), поэтому безопасно
    вызывать на буфере, который native-код переиспользует после возврата
    из callback.

    `sample_format` определяет, как физически закодирован один отсчёт:
    INT8 (HackRF) — знаковый байт, нормировка делением на 128;
    UINT8 (RTL-SDR) — беззнаковый байт со смещением 127.5, та же нормировка
    после вычитания смещения.
    """
    if sample_format is SampleFormat.INT8:
        signed = raw.view(np.int8)
        scaled = signed.astype(np.float32)
        scaled *= 1.0 / _INT8_FULL_SCALE
    elif sample_format is SampleFormat.UINT8:
        unsigned = raw.view(np.uint8)
        scaled = unsigned.astype(np.float32)
        scaled -= _UINT8_MIDPOINT
        scaled *= 1.0 / _UINT8_FULL_SCALE
    else:
        raise ValueError(f"Unknown sample_format={sample_format!r}")
    # complex64 в памяти = пары float32 (re, im) подряд — ровно наш
    # чередующийся порядок I,Q после нормировки. Это переинтерпретация без
    # копирования, а не арифметика.
    return scaled.view(np.complex64)


class IQStreamReader:
    """Подписывается на приём устройства, публикует IQBlock через очередь.

    Callback устройства исполняется в потоке, управляемом самим устройством
    (libusb-поток у HackRF, отдельный поток rtlsdr_read_async у RTL-SDR) —
    внутри него выполняется только минимально необходимая работа (конвертация
    буфера в complex64 и постановка блока в очередь). Блокироваться в
    callback нельзя: не вернувшись быстро, поток тормозит приём.

    При переполнении очереди (потребитель не успевает разбирать блоки)
    новый блок отбрасывается, а не ожидается свободное место.
    """

    def __init__(
        self,
        device: SdrDevice,
        radio_config: RadioConfig,
        acquisition_config: AcquisitionConfig,
    ) -> None:
        self._device = device
        self._sample_format = device.sample_format
        self._sample_rate_hz = radio_config.sample_rate_hz
        self._settle_sample_count = round(radio_config.settle_time_s * radio_config.sample_rate_hz)
        self._queue: queue.Queue[IQBlock] = queue.Queue(
            maxsize=acquisition_config.queue_max_blocks
        )

        self._stream_start_utc: datetime | None = None
        self._next_sample_index = 0
        self._dropped_blocks = 0
        self._received_blocks = 0
        self._received_samples = 0
        self._discarded_settle_blocks = 0

    def start(self) -> None:
        self._stream_start_utc = datetime.now(timezone.utc)
        self._next_sample_index = 0
        self._dropped_blocks = 0
        self._received_blocks = 0
        self._received_samples = 0
        self._discarded_settle_blocks = 0
        self._device.start_rx(self._on_samples)

    def stop(self) -> None:
        self._device.stop_rx()

    def get_block(self, timeout: float | None = None) -> IQBlock:
        """Забирает следующий блок из очереди. Бросает queue.Empty по таймауту."""
        return self._queue.get(timeout=timeout)

    @property
    def dropped_blocks(self) -> int:
        """Приблизительное значение — читается из другого потока без блокировки.

        Используется только для отображения живой статистики, не для
        логики, критичной к точности.
        """
        return self._dropped_blocks

    @property
    def received_blocks(self) -> int:
        return self._received_blocks

    @property
    def received_samples(self) -> int:
        return self._received_samples

    @property
    def discarded_settle_blocks(self) -> int:
        """Сколько блоков отброшено как относящиеся к окну устаканивания приёмника."""
        return self._discarded_settle_blocks

    def _on_samples(self, raw: np.ndarray) -> None:
        valid_length = raw.shape[0]
        if valid_length % 2 != 0:
            _logger.warning(
                "Odd IQ block length (%d bytes), dropping the last byte",
                valid_length,
            )
            valid_length -= 1
        if valid_length <= 0:
            return

        n_samples = valid_length // 2
        block_start_index = self._next_sample_index
        self._next_sample_index += n_samples
        self._received_blocks += 1
        self._received_samples += n_samples

        if block_start_index + n_samples <= self._settle_sample_count:
            # Приёмник ещё не устаканился после старта приёма (PLL/AGC/DC-сервус
            # у HackRF, переходный процесс тюнера у RTL-SDR) — блок физически
            # принят и учтён в статистике, но намеренно не доходит до потребителя.
            self._discarded_settle_blocks += 1
            return

        complex_samples = convert_raw_iq_to_complex64(raw[:valid_length], self._sample_format)

        block = IQBlock(
            samples=complex_samples,
            sample_index=block_start_index,
            sample_rate_hz=self._sample_rate_hz,
            stream_start_utc=self._stream_start_utc,
        )

        try:
            self._queue.put_nowait(block)
        except queue.Full:
            self._dropped_blocks += 1
