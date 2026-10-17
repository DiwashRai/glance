"""The counts the collector (update_status.py) writes, for the HUD.

The file is `{"f": [[label, icon, count, level], ...]}`: level 0 to 3 from the entry's thresholds,
and a count of -1 when its provider failed. It's read only when it changes, so a file that can't
be read reports once (through the error hook), not on every check.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import msgspec


@dataclass(frozen=True)
class Count:
    label: str
    icon: str
    value: int  # -1: the provider failed
    level: int  # 0 to 3


Value = Annotated[int, msgspec.Meta(ge=-1)]
Level = Annotated[int, msgspec.Meta(ge=0, le=3)]


class _File(msgspec.Struct, frozen=True):
    f: tuple[tuple[str, str, Value, Level], ...]  # required: a file without it is refused


class CountsFile:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.seen = (0, -1)  # (modified time, size) last read
        self.counts: tuple[Count, ...] = ()

    def read(self) -> tuple[Count, ...]:
        """The latest counts: re-read only if the file changed, and () if there's no file."""
        stamp = _stamp(self.path)
        if stamp == self.seen:
            return self.counts
        # Before decoding: a bad file is reported once, not on every check, and shows no counts
        # rather than old ones that look current.
        self.seen, self.counts = stamp, ()
        rows = msgspec.json.decode(self.path.read_bytes(), type=_File).f if stamp[1] >= 0 else ()
        self.counts = tuple(Count(label, icon, value, level) for label, icon, value, level in rows)
        return self.counts


def _stamp(path: Path) -> tuple[int, int]:
    if not path.exists():
        return (0, -1)
    info = path.stat()
    return (info.st_mtime_ns, info.st_size)
