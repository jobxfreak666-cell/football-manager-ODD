import errno
import os
import tempfile
from pathlib import Path

import pytest

import windows_temp_cleanup as cleanup


def _error(path, code=145):
    error = OSError(errno.ENOTEMPTY, "directory not empty", str(path))
    error.winerror = code
    return error


def test_empty_delete_pending_root_can_finish(tmp_path, monkeypatch):
    root = tmp_path / "empty"
    root.mkdir()
    calls = []
    original = cleanup._rmdir

    def remove(path):
        calls.append(path)
        if len(calls) == 1:
            raise _error(path)
        original(path)

    monkeypatch.setattr(cleanup, "_rmdir", remove)
    monkeypatch.setattr(cleanup, "_sleep", lambda _delay: None)
    cleanup.finish_empty_temp_root(str(root), _error(root))
    assert not root.exists()
    assert len(calls) == 2


@pytest.mark.parametrize("case", ["nonempty", "other_error", "other_path"])
def test_cleanup_keeps_nonempty_or_unrelated_failures(tmp_path, monkeypatch, case):
    root = tmp_path / "root"
    root.mkdir()
    original_error = _error(root)
    if case == "nonempty":
        (root / "keep.txt").write_text("keep", encoding="utf-8")
    elif case == "other_error":
        original_error = _error(root, 5)
    else:
        original_error = _error(tmp_path / "other")
    calls = []
    monkeypatch.setattr(cleanup, "_rmdir", lambda path: calls.append(path))
    with pytest.raises(OSError) as caught:
        cleanup.finish_empty_temp_root(str(root), original_error)
    assert caught.value is original_error
    assert calls == []
    assert root.is_dir()
    if case == "nonempty":
        assert (root / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_new_file_during_wait_is_preserved(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    calls = []

    def concurrent_writer(path):
        calls.append(path)
        (root / "keep.txt").write_text("new", encoding="utf-8")
        raise _error(path)

    monkeypatch.setattr(cleanup, "_rmdir", concurrent_writer)
    monkeypatch.setattr(cleanup, "_sleep", lambda _delay: None)
    with pytest.raises(OSError):
        cleanup.finish_empty_temp_root(str(root), _error(root))
    assert len(calls) == 1
    assert (root / "keep.txt").read_text(encoding="utf-8") == "new"


def test_persistent_empty_root_failure_is_bounded(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    calls = []
    failure = _error(root)

    def unavailable(path):
        calls.append(path)
        raise failure

    monkeypatch.setattr(cleanup, "_rmdir", unavailable)
    monkeypatch.setattr(cleanup, "_sleep", lambda _delay: None)
    with pytest.raises(OSError) as caught:
        cleanup.finish_empty_temp_root(str(root), failure, max_attempts=3)
    assert caught.value is failure
    assert len(calls) == 3


@pytest.mark.skipif(os.name != "nt", reason="Exercises the Windows-only pytest cleanup fixture")
def test_windows_fixture_calls_original_cleanup_only_once(monkeypatch):
    calls = []

    def blocked_root(cls, name, *args, **kwargs):
        calls.append(name)
        raise _error(name)

    monkeypatch.setattr(tempfile.TemporaryDirectory, "_rmtree", classmethod(blocked_root))
    monkeypatch.setattr(cleanup, "_sleep", lambda _delay: None)
    with pytest.warns(pytest.PytestWarning, match="Recovered Windows error 145"):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            assert root.is_dir()
    assert not root.exists()
    assert calls == [name]
