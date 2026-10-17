"""The counts the collector (update_status.py) writes, for the HUD.

The file is `{"f": [[label, icon, count, level], ...]}`: level 0 to 3 from the entry's thresholds,
and a count of -1 when its provider failed. It's read only when it changes, so a file that can't
be read reports once (through the error hook), not on every check.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import msgspec


class Count(msgspec.Struct, frozen=True, array_like=True):  # a row is a list, not an object
    label: str
    icon: str
    value: Annotated[int, msgspec.Meta(ge=-1)]  # -1: the provider failed
    level: Annotated[int, msgspec.Meta(ge=0, le=3)]


class _File(msgspec.Struct, frozen=True):
    f: tuple[Count, ...]  # required: a file without it is refused


class CountsFile:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.seen = b""  # the file's bytes when last decoded
        self.counts: tuple[Count, ...] = ()

    def read(self) -> tuple[Count, ...]:
        """The latest counts: decoded again only if the file's bytes changed, and () if there's
        no file (or it's empty). The bytes, not the modified time: two writes in quick succession
        can share a time, and the file is tiny."""
        raw = self.path.read_bytes() if self.path.exists() else b""
        if raw == self.seen:
            return self.counts
        # Before decoding: a bad file is reported once, not on every check, and shows no counts
        # rather than old ones that look current.
        self.seen, self.counts = raw, ()
        if raw:
            self.counts = msgspec.json.decode(raw, type=_File).f
        return self.counts
