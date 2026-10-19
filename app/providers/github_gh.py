"""Pull requests, from the GitHub CLI: each request is the arguments for one `gh search prs`, and
a PR found by more than one counts once."""

from collections.abc import Sequence
from typing import Annotated

import msgspec

from app.types import NonEmpty, Table
from app.utils import run_no_window


class _Request(msgspec.Struct):
    args: Annotated[tuple[NonEmpty, ...], msgspec.Meta(min_length=1)]


class _Pr(msgspec.Struct):
    url: str


def count(_provider: Table, requests: Sequence[Table]) -> int:
    """`gh` has its own login, so `[providers.<name>]` needs nothing but its kind."""
    searches = [msgspec.convert(request, _Request).args for request in requests]  # all, first
    urls: set[str] = set()
    for args in searches:
        completed = run_no_window(["gh", "search", "prs", "--json", "url", *args])
        if completed.returncode != 0:
            message = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(
                f"gh search prs failed with exit code {completed.returncode}: {message}"
            )
        urls.update(pr.url for pr in msgspec.json.decode(completed.stdout, type=tuple[_Pr, ...]))
    return len(urls)
