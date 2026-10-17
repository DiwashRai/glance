from pathlib import Path

import msgspec
import pytest

from app.counts import Count, CountsFile


def test_reads_the_collectors_file_and_rereads_when_it_changes(tmp_path: Path) -> None:
    path = tmp_path / "status.json"
    counts = CountsFile(path)
    assert counts.read() == ()  # no file yet
    path.write_text('{"f": [["mail", "M", 18, 2], ["jira", "J", -1, 3]]}', encoding="utf-8")
    assert counts.read() == (Count("mail", "M", 18, 2), Count("jira", "J", -1, 3))
    path.write_text('{"f": [["mail", "M", 3, 0]]}', encoding="utf-8")
    assert counts.read() == (Count("mail", "M", 3, 0),)


@pytest.mark.parametrize(
    "bad",
    [
        '{"f": [["mail", "M", "lots", 2]]}',
        '{"f": [["mail", "M", -2, 2]]}',
        '{"f": [["mail", "M", 1, 4]]}',
        "{}",
    ],
)
def test_a_bad_file_is_refused_once_and_shows_no_stale_counts(tmp_path: Path, bad: str) -> None:
    path = tmp_path / "status.json"
    path.write_text('{"f": [["mail", "M", 18, 2]]}', encoding="utf-8")
    counts = CountsFile(path)
    assert counts.read() == (Count("mail", "M", 18, 2),)
    path.write_text(bad, encoding="utf-8")
    with pytest.raises(msgspec.ValidationError):
        counts.read()
    assert counts.read() == ()  # unchanged since: not reported again, and no old counts
