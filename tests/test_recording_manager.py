from datetime import datetime, timezone

import pytest

from sdr_monitor.audio import recording_manager as recording_manager_module
from sdr_monitor.audio.recording_manager import RecordingManager
from sdr_monitor.detection.active_signal import ActiveSignal
from sdr_monitor.detection.detected_signal import DetectedSignal

_START = datetime(2026, 1, 1, tzinfo=timezone.utc)


class _FakeChannelRecorder:
    """Имитирует состояния настоящего ChannelRecorder: begin_closing() может
    закрыть сразу (next_post_roll_blocks=0, по умолчанию) либо потребовать ещё
    N вызовов process() перед is_done (имитация post-roll)."""

    instances: list["_FakeChannelRecorder"] = []
    created_count = 0
    next_post_roll_blocks = 0
    next_was_recorded = True

    def __init__(self) -> None:
        self.processed_blocks = []
        self.closed = False
        self._is_done = False
        self._closing = False
        self._post_roll_blocks_remaining = _FakeChannelRecorder.next_post_roll_blocks
        self._was_recorded = _FakeChannelRecorder.next_was_recorded

    @classmethod
    def create(cls, audio_config, radio_config, track_id, center_frequency_hz, start_time_utc):
        cls.created_count += 1
        instance = cls()
        instance.track_id = track_id
        instance.center_frequency_hz = center_frequency_hz
        instance.start_time_utc = start_time_utc
        cls.instances.append(instance)
        return instance

    @property
    def is_done(self) -> bool:
        return self._is_done

    def process(self, block) -> None:
        self.processed_blocks.append(block)
        if self._closing:
            self._post_roll_blocks_remaining -= 1
            if self._post_roll_blocks_remaining <= 0:
                self._is_done = True

    def begin_closing(self) -> bool:
        if not self._was_recorded:
            self._is_done = True
            return False
        self._closing = True
        if self._post_roll_blocks_remaining <= 0:
            self._is_done = True
        return True

    def close_immediately(self) -> None:
        self.closed = True
        self._is_done = True


@pytest.fixture(autouse=True)
def _reset_fake():
    _FakeChannelRecorder.instances = []
    _FakeChannelRecorder.created_count = 0
    _FakeChannelRecorder.next_post_roll_blocks = 0
    _FakeChannelRecorder.next_was_recorded = True
    yield


def _active_signal(track_id: int, frequency_hz: float = 127_900_000.0) -> ActiveSignal:
    return ActiveSignal(
        track_id=track_id,
        center_frequency_hz=frequency_hz,
        current_level_db=-30.0,
        current_snr_db=15.0,
        peak_level_db=-28.0,
        peak_snr_db=17.0,
        start_time_utc=_START,
        elapsed_s=1.0,
    )


def _detected_signal(track_id: int, frequency_hz: float = 127_900_000.0) -> DetectedSignal:
    return DetectedSignal(
        track_id=track_id,
        center_frequency_hz=frequency_hz,
        peak_level_db=-28.0,
        peak_snr_db=17.0,
        start_time_utc=_START,
        end_time_utc=_START,
        duration_s=3.0,
    )


def test_opens_recorder_only_once_per_track(monkeypatch):
    monkeypatch.setattr(recording_manager_module, "ChannelRecorder", _FakeChannelRecorder)
    manager = RecordingManager(audio_config=object(), radio_config=object())
    signal = _active_signal(track_id=1)

    manager.on_active_signals([signal])
    manager.on_active_signals([signal])

    assert _FakeChannelRecorder.created_count == 1


def test_finalize_with_no_post_roll_removes_recorder_immediately(monkeypatch):
    monkeypatch.setattr(recording_manager_module, "ChannelRecorder", _FakeChannelRecorder)
    manager = RecordingManager(audio_config=object(), radio_config=object())
    manager.on_active_signals([_active_signal(track_id=1)])
    recorder = _FakeChannelRecorder.instances[0]

    was_recorded = manager.on_signal_finalized(_detected_signal(track_id=1))

    assert was_recorded is True
    assert recorder.is_done is True

    manager.process_block(object())
    assert recorder.processed_blocks == []  # уже удалён, блоков больше не получает


def test_finalize_of_short_signal_reports_not_recorded(monkeypatch):
    monkeypatch.setattr(recording_manager_module, "ChannelRecorder", _FakeChannelRecorder)
    _FakeChannelRecorder.next_was_recorded = False
    manager = RecordingManager(audio_config=object(), radio_config=object())
    manager.on_active_signals([_active_signal(track_id=1)])
    recorder = _FakeChannelRecorder.instances[0]

    was_recorded = manager.on_signal_finalized(_detected_signal(track_id=1))

    assert was_recorded is False  # короче min_recording_duration_s, файл не создан
    assert recorder.is_done is True


def test_finalize_with_post_roll_keeps_receiving_blocks_until_done(monkeypatch):
    monkeypatch.setattr(recording_manager_module, "ChannelRecorder", _FakeChannelRecorder)
    _FakeChannelRecorder.next_post_roll_blocks = 2
    manager = RecordingManager(audio_config=object(), radio_config=object())
    manager.on_active_signals([_active_signal(track_id=1)])
    recorder = _FakeChannelRecorder.instances[0]

    was_recorded = manager.on_signal_finalized(_detected_signal(track_id=1))
    assert was_recorded is True
    assert recorder.is_done is False  # ещё не готов, нужно 2 блока post-roll

    manager.process_block(object())
    assert recorder.is_done is False
    manager.process_block(object())
    assert recorder.is_done is True

    manager.process_block(object())
    assert len(recorder.processed_blocks) == 2  # третий блок уже не дошёл (удалён после is_done)


def test_on_signal_finalized_for_unknown_track_is_noop(monkeypatch):
    monkeypatch.setattr(recording_manager_module, "ChannelRecorder", _FakeChannelRecorder)
    manager = RecordingManager(audio_config=object(), radio_config=object())

    was_recorded = manager.on_signal_finalized(_detected_signal(track_id=99))  # не должно бросать
    assert was_recorded is False


def test_process_block_dispatches_to_all_open_recorders(monkeypatch):
    monkeypatch.setattr(recording_manager_module, "ChannelRecorder", _FakeChannelRecorder)
    manager = RecordingManager(audio_config=object(), radio_config=object())
    manager.on_active_signals(
        [_active_signal(track_id=1), _active_signal(track_id=2, frequency_hz=126_900_000.0)]
    )

    block = object()
    manager.process_block(block)

    assert len(_FakeChannelRecorder.instances) == 2
    for recorder in _FakeChannelRecorder.instances:
        assert recorder.processed_blocks == [block]


def test_close_all_closes_every_open_recorder(monkeypatch):
    monkeypatch.setattr(recording_manager_module, "ChannelRecorder", _FakeChannelRecorder)
    manager = RecordingManager(audio_config=object(), radio_config=object())
    manager.on_active_signals([_active_signal(track_id=1), _active_signal(track_id=2)])

    manager.close_all()

    assert all(recorder.closed for recorder in _FakeChannelRecorder.instances)

    manager.process_block(object())
    assert all(recorder.processed_blocks == [] for recorder in _FakeChannelRecorder.instances)
