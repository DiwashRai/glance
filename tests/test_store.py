from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core.model import Event, Lists, ParkedTask, Task, Waiting
from app.store import NO_FILE, Snapshot, Store, Unreadable

AT = datetime(2026, 10, 17, 9, 58, 40, tzinfo=timezone(timedelta(hours=1)))
LISTS = Lists(Task("Do ticket 1234"), (ParkedTask(Task("1129 reset"), Waiting("review")),))


def snapshot(store: Store) -> Snapshot:
    match store.load():
        case Snapshot() as loaded:
            return loaded
        case Unreadable() as unreadable:
            pytest.fail(unreadable.message)


def test_first_load_is_empty_and_creates_the_folder(tmp_path: Path) -> None:
    store = Store(tmp_path / "new" / "glance")
    assert snapshot(store) == Snapshot(Lists(), NO_FILE)
    assert store.folder.is_dir()
    assert not store.tasks_path.exists()


def test_save_then_load(tmp_path: Path) -> None:
    store = Store(tmp_path)
    stamp = store.save(LISTS)
    assert snapshot(store) == Snapshot(LISTS, stamp)
    assert not (tmp_path / "tasks.md.tmp").exists()
    assert b"\r\n" not in store.tasks_path.read_bytes()


def test_an_outside_edit_changes_the_stamp(tmp_path: Path) -> None:
    store = Store(tmp_path)
    stamp = store.save(LISTS)
    store.tasks_path.write_text("# Active\n- edited by hand\n", encoding="utf-8")
    assert store.stamp() != stamp
    assert snapshot(store).lists == Lists(Task("edited by hand"), ())


def test_an_unreadable_file_is_refused_and_left_alone(tmp_path: Path) -> None:
    store = Store(tmp_path)
    store.tasks_path.write_text("# Active\n- a\n- b\n", encoding="utf-8")
    match store.load():
        case Unreadable() as unreadable:
            assert unreadable.message == "tasks.md line 3: only one task can be active"
        case Snapshot():
            pytest.fail("expected the file to be refused")
    assert store.tasks_path.read_text(encoding="utf-8") == "# Active\n- a\n- b\n"


def test_events_are_appended_as_aligned_lines(tmp_path: Path) -> None:
    store = Store(tmp_path)
    store.append([Event(AT, "started", "Do ticket 1234")])
    store.append([Event(AT, "parked", "a · b", "left off: retry loop")])
    assert store.events_path.read_text(encoding="utf-8").splitlines() == [
        "2026-10-17 09:58:40+01:00  started    Do ticket 1234",
        "2026-10-17 09:58:40+01:00  parked     a - b · left off: retry loop",
    ]
