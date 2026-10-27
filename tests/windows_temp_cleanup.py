"""Finish Windows delete-pending cleanup without deleting newly created files."""

from __future__ import annotations

import os
import stat
from time import sleep as _sleep


_rmdir = os.rmdir


def _matches_root(error: OSError, path: str) -> bool:
    return (
        getattr(error, "winerror", None) == 145
        and error.filename is not None
        and os.path.normcase(os.path.abspath(error.filename))
        == os.path.normcase(os.path.abspath(path))
    )


def finish_empty_temp_root(path: str, error: OSError, *, max_attempts: int = 10) -> None:
    """Retry only the empty root's rmdir, never its recursive cleanup."""
    for _attempt in range(max_attempts):
        if not _matches_root(error, path):
            raise error
        metadata = os.lstat(path)
        plain_directory = (
            stat.S_ISDIR(metadata.st_mode)
            and not stat.S_ISLNK(metadata.st_mode)
            and not (
                getattr(metadata, "st_file_attributes", 0)
                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            )
        )
        if not plain_directory:
            raise error
        with os.scandir(path) as entries:
            empty = next(entries, None) is None
        if not empty:
            raise error
        _sleep(0.02)
        try:
            _rmdir(path)
            return
        except OSError as next_error:
            error = next_error
    raise error
