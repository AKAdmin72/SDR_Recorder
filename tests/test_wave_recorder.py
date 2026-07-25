import wave
from pathlib import Path

import numpy as np

from sdr_monitor.audio.wave_recorder import WaveRecorder


def test_writes_valid_wav_file(tmp_path: Path):
    file_path = tmp_path / "test.wav"
    recorder = WaveRecorder(file_path, sample_rate_hz=16000, pcm_full_scale_input=1.0)

    recorder.write(np.array([0.5, -0.5, 0.0], dtype=np.float32))
    recorder.close()

    with wave.open(str(file_path), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 16000
        assert wf.getnframes() == 3
        raw = wf.readframes(3)
        samples = np.frombuffer(raw, dtype=np.int16)
        np.testing.assert_array_equal(samples, [16383, -16383, 0])


def test_clips_out_of_range_values(tmp_path: Path):
    file_path = tmp_path / "clip.wav"
    recorder = WaveRecorder(file_path, sample_rate_hz=16000, pcm_full_scale_input=1.0)

    recorder.write(np.array([10.0, -10.0], dtype=np.float32))
    recorder.close()

    with wave.open(str(file_path), "rb") as wf:
        samples = np.frombuffer(wf.readframes(2), dtype=np.int16)
        assert samples[0] == 32767
        assert samples[1] == -32768


def test_creates_parent_directory(tmp_path: Path):
    file_path = tmp_path / "nested" / "dir" / "test.wav"
    recorder = WaveRecorder(file_path, sample_rate_hz=16000, pcm_full_scale_input=1.0)

    recorder.write(np.array([0.0], dtype=np.float32))
    recorder.close()

    assert file_path.exists()


def test_write_empty_array_is_noop(tmp_path: Path):
    file_path = tmp_path / "empty.wav"
    recorder = WaveRecorder(file_path, sample_rate_hz=16000, pcm_full_scale_input=1.0)

    recorder.write(np.empty(0, dtype=np.float32))
    recorder.close()

    with wave.open(str(file_path), "rb") as wf:
        assert wf.getnframes() == 0
