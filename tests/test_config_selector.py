from pathlib import Path

import pytest

from sdr_monitor.config_selector import select_config_path


def _fail_if_called(prompt: str) -> str:
    raise AssertionError(f"input_func не должен был вызываться (prompt={prompt!r})")


def test_explicit_path_returned_without_scanning(tmp_path):
    explicit = tmp_path / "somewhere.toml"
    result = select_config_path(tmp_path, explicit, input_func=_fail_if_called)
    assert result == explicit


def test_single_candidate_returned_without_prompt(tmp_path):
    (tmp_path / "only.toml").write_text("", encoding="utf-8")

    result = select_config_path(tmp_path, None, input_func=_fail_if_called)

    assert result == tmp_path / "only.toml"


def test_empty_directory_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        select_config_path(tmp_path, None, input_func=_fail_if_called)


def _make_three(tmp_path: Path) -> None:
    (tmp_path / "app_config.toml").write_text("", encoding="utf-8")
    (tmp_path / "rtl_126_3_am.toml").write_text("", encoding="utf-8")
    (tmp_path / "rtl_155_1_am.toml").write_text("", encoding="utf-8")


def test_multiple_candidates_picks_by_number(tmp_path, monkeypatch):
    _make_three(tmp_path)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    result = select_config_path(tmp_path, None, input_func=lambda _p: "2")

    assert result == tmp_path / "rtl_126_3_am.toml"  # второй по алфавиту


def test_multiple_candidates_empty_input_picks_app_config(tmp_path, monkeypatch):
    _make_three(tmp_path)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    result = select_config_path(tmp_path, None, input_func=lambda _p: "")

    assert result == tmp_path / "app_config.toml"


def test_multiple_candidates_empty_input_picks_first_alphabetically_without_app_config(
    tmp_path, monkeypatch
):
    (tmp_path / "rtl_126_3_am.toml").write_text("", encoding="utf-8")
    (tmp_path / "rtl_155_1_am.toml").write_text("", encoding="utf-8")
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    result = select_config_path(tmp_path, None, input_func=lambda _p: "")

    assert result == tmp_path / "rtl_126_3_am.toml"


def test_invalid_input_then_valid_reprompts(tmp_path, monkeypatch):
    _make_three(tmp_path)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    responses = iter(["not_a_number", "99", "3"])

    result = select_config_path(tmp_path, None, input_func=lambda _p: next(responses))

    assert result == tmp_path / "rtl_155_1_am.toml"  # третий по алфавиту


def test_non_tty_skips_prompt_and_uses_default(tmp_path, monkeypatch):
    _make_three(tmp_path)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)

    result = select_config_path(tmp_path, None, input_func=_fail_if_called)

    assert result == tmp_path / "app_config.toml"
