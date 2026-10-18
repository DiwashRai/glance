from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.controller import Controller, View
from app.core.model import CommandWords, Idle, Lists, Task
from app.core.today import Span
from app.store import Store

NOW = datetime(2026, 10, 17, 9, 58, 40, tzinfo=timezone(timedelta(hours=1)))


def controller(folder: Path) -> Controller:
    return Controller(Store(folder), CommandWords(), lambda: NOW)


def test_a_command_is_saved_then_shown_then_logged(tmp_path: Path) -> None:
    glance = controller(tmp_path)
    glance.open()
    view = glance.run("new fix the build")
    assert view == View(Lists(Task("fix the build"), ()), "started fix the build", accepted=True)
    assert controller(tmp_path).open().lists == view.lists  # saved: a fresh start sees it
    assert not (tmp_path / "events.log").exists()  # history is written after drawing
    assert glance.day().spans == (Span("fix the build", NOW, NOW, going=True),)  # already
    glance.write_history()
    assert (tmp_path / "events.log").read_text(encoding="utf-8").count("\n") == 1
    glance.open()  # read back from events.log, not counted twice
    assert glance.day().spans == (Span("fix the build", NOW, NOW, going=True),)


def test_a_rejection_changes_nothing_and_keeps_the_text(tmp_path: Path) -> None:
    glance = controller(tmp_path)
    glance.open()
    assert glance.run("done") == View(Lists(), "nothing is active")
    assert not (tmp_path / "tasks.md").exists()


def test_a_failed_save_leaves_memory_unchanged(tmp_path: Path) -> None:
    glance = controller(tmp_path)
    glance.open()
    (tmp_path / "tasks.md.tmp").mkdir()  # the save's temp file can't be written
    with pytest.raises(OSError):
        glance.run("new lost")
    assert glance.lists == Lists()
    (tmp_path / "tasks.md.tmp").rmdir()
    assert glance.run("new kept").message == "started kept"  # no false "tasks.md changed"


def test_an_edit_after_opening_reloads_instead_of_guessing(tmp_path: Path) -> None:
    glance = controller(tmp_path)
    glance.open()
    glance.run("new first")
    (tmp_path / "tasks.md").write_text("# Active\n- edited by hand\n", encoding="utf-8")
    view = glance.run("done")
    assert view == View(Lists(Task("edited by hand"), ()), "tasks.md changed, run it again")
    assert glance.run("done").message == "finished edited by hand"


@pytest.mark.parametrize(
    ("content", "problem"),
    [
        (b"# Active\n- a\n- b\n", "tasks.md line 3: only one task can be active"),
        (b"# Active\n- caf\xe9\n", "tasks.md line 2: this isn't UTF-8 text"),
    ],
)
def test_an_unreadable_file_refuses_commands_until_fixed(
    tmp_path: Path, content: bytes, problem: str
) -> None:
    (tmp_path / "tasks.md").write_bytes(content)
    glance = controller(tmp_path)
    assert glance.open().problem.startswith(problem)
    assert glance.run("done").problem.startswith(problem)
    assert (tmp_path / "tasks.md").read_bytes() == content
    (tmp_path / "tasks.md").write_text("# Active\n- fixed\n", encoding="utf-8")
    assert glance.run("done") == View(Lists(Task("fixed"), ()), "tasks.md changed, run it again")
    assert glance.run("done").lists == Lists(Idle(), ())


def test_todays_blocks_are_put_on_the_clock(tmp_path: Path) -> None:
    glance = controller(tmp_path)
    glance.open()
    glance.run("block 14:00 1h deep work")
    (slot,) = glance.day().slots
    assert (slot.number, slot.block.what, slot.start.hour) == (1, "deep work", 14)
    assert slot.end - slot.start == timedelta(hours=1)
