"""Made-up counts for trying glance out: each run, a key's last count (or its start) minus a step,
down to 0."""

from collections.abc import Sequence
from pathlib import Path

import msgspec

from app.types import CountsRow, NonEmpty, Table


class _Config(msgspec.Struct):
    output_path: NonEmpty  # the counts file, where the last counts are read from


class _Request(msgspec.Struct):
    key: NonEmpty
    start: int
    step: int = 5


class _Counts(msgspec.Struct):
    f: tuple[CountsRow, ...] = ()


def count(provider: Table, requests: Sequence[Table]) -> int:
    path = Path(msgspec.convert(provider, _Config).output_path)
    rows = msgspec.json.decode(path.read_bytes(), type=_Counts).f if path.is_file() else ()
    last = {label: number for label, _, number, _ in rows}
    asked = [msgspec.convert(request, _Request) for request in requests]
    return sum(max(last.get(request.key, request.start) - request.step, 0) for request in asked)
