from __future__ import annotations

import os
import time
from pathlib import Path


def atomic_write_text(path: Path, text: str, *, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    if mode is not None:
        os.chmod(temporary, mode)

    last_error: PermissionError | None = None
    for attempt in range(6):
        try:
            temporary.replace(path)
            if mode is not None:
                os.chmod(path, mode)
            return
        except PermissionError as error:
            last_error = error
            time.sleep(0.05 * (attempt + 1))

    try:
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(path, mode)
    finally:
        temporary.unlink(missing_ok=True)
