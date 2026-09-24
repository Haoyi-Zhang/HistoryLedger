from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator

from .model import History


@contextmanager
def atomic_output_path(path: str | Path) -> Iterator[Path]:
    """Yield a sibling temporary path and publish it atomically on success.

    Existing evidence is never replaced by a partial file. A later invocation
    removes stale temporary siblings left by an uncatchable process kill. The
    artifact uses one worker, so cleanup cannot race another writer.
    """
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    prefix = f".{destination.name}."
    suffix = ".tmp"
    for stale in destination.parent.glob(f"{prefix}*{suffix}"):
        stale.unlink(missing_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=prefix, suffix=suffix, dir=destination.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        yield temporary
        descriptor = os.open(temporary, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, destination)
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        try:
            directory_descriptor = os.open(destination.parent, directory_flags)
        except OSError:
            directory_descriptor = -1
        if directory_descriptor >= 0:
            try:
                try:
                    os.fsync(directory_descriptor)
                except OSError:
                    pass
            finally:
                os.close(directory_descriptor)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def atomic_write_text(
    path: str | Path, text: str, *, encoding: str = "utf-8"
) -> None:
    with atomic_output_path(path) as temporary:
        temporary.write_text(text, encoding=encoding)


def atomic_write_json(path: str | Path, payload: object) -> None:
    atomic_write_text(
        path, json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def load_histories(path: str | Path) -> list[History]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    raw_histories = data["histories"] if isinstance(data, dict) else data
    return [History.from_dict(item) for item in raw_histories]


def save_histories(path: str | Path, histories: Iterable[History], metadata: dict | None = None) -> None:
    payload = {
        "metadata": metadata or {},
        "histories": [history.to_dict() for history in histories],
    }
    atomic_write_json(path, payload)
