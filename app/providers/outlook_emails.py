"""Unread mail in Outlook, from get_outlook_unread.ps1. Each request lists folders: a name (from
the store), or a number for one of Outlook's default folders (6 is the Inbox)."""

import functools
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated

import msgspec

from app.types import NonEmpty, Table
from app.utils import run_no_window

_SCRIPT_PATH = Path(__file__).with_name("get_outlook_unread.ps1")
Unread = Annotated[int, msgspec.Meta(ge=0)]


class _Config(msgspec.Struct):
    outlook_store: NonEmpty  # its email address


class _Request(msgspec.Struct):
    folders: Annotated[tuple[NonEmpty, ...], msgspec.Meta(min_length=1)]


class _Failed(msgspec.Struct):
    error: str = ""  # the script's only key when it fails


def count(provider: Table, requests: Sequence[Table]) -> int:
    store = msgspec.convert(provider, _Config).outlook_store.lower()
    folders = [name for request in requests for name in msgspec.convert(request, _Request).folders]
    numbered = {name: str(int(name)) for name in folders if name.isdigit()}  # "06" is 6
    counts = unread(store, tuple(sorted(set(numbered.values()))))
    return sum(
        counts["default"][numbered[name]] if name in numbered else counts[store][name.lower()]
        for name in folders
    )


@functools.cache
def unread(store: str, numbered: tuple[str, ...]) -> dict[str, dict[str, Unread]]:
    """Unread counts by folder: the store's under its address, the numbered ones under "default".
    The script runs once a run for each store and set of numbers, however many entries ask."""
    command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass"]
    command += ["-File", str(_SCRIPT_PATH), "-Store", store]
    command += ["-DefaultFolderIds", ",".join(numbered)] if numbered else []
    completed = run_no_window(command)
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(
            f"get_outlook_unread.ps1 failed with exit code {completed.returncode}: {message}"
        )
    failed = msgspec.json.decode(completed.stdout, type=_Failed).error
    if failed:
        raise RuntimeError(failed)
    # the script gives -1 for a folder it can't open: refused here, so only this entry fails
    return msgspec.json.decode(completed.stdout, type=dict[str, dict[str, Unread]])
