from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.controller import Controller, View
from app.core.model import CommandWords, Idle, Lists, Task
from app.core.today import Span
from app.store import Store

NOW = datetime(2026, 10, 17, 9, 58, 40, tzinfo=timezone(timedelta(hours=1)))


class Agents:
    """herdr, as the controller sees it: who's running, and what each was sent."""

    def __init__(self, *running: str) -> None:
        self.up = set(running)
        self.asked = 0  # how many times it was asked who's running
        self.sent: list[tuple[str, str]] = []

    def check(self, name: str) -> str:
        self.asked += 1
        return "" if name in self.up else f"{name} isn't running"

    def send(self, name: str, text: str) -> str:
        if name not in self.up:
            return f"{name} isn't running"
        self.sent.append((name, text))
        return ""


def controller(folder: Path, agents: Agents | None = None) -> Controller:
    return Controller(Store(folder), CommandWords(), lambda: NOW, agents or Agents())


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


def test_spaces_first_send_the_line_to_an_agent_and_nothing_else(tmp_path: Path) -> None:
    agents = Agents("assistant", "chief")
    glance = controller(tmp_path, agents)
    glance.open()
    assert glance.run(" done") == View(Lists(), "sent to assistant", accepted=True)
    assert glance.run("   ask backend for the API ").message == "sent to chief"
    assert agents.sent == [("assistant", "done"), ("chief", "ask backend for the API")]
    assert glance.run("   ") == View(Lists(), accepted=True)  # only spaces: nothing sent
    assert not (tmp_path / "tasks.md").exists()


def test_enter_on_an_empty_line_clears_the_top_message_and_so_does_answering_it(
    tmp_path: Path,
) -> None:
    store = Store(tmp_path)
    for minute, sender in enumerate(("chief", "assistant", "chief")):
        store.tell(sender, f"message {minute}", NOW + timedelta(minutes=minute))
    agents = Agents("assistant", "chief")
    glance = controller(tmp_path, agents)
    glance.open()
    glance.run(" for assistant")  # chief's is on top: answering someone else leaves it
    assert [message.text for message in glance.inbox] == ["message 0", "message 1", "message 2"]
    glance.run("  yes, post them")
    glance.run("")
    assert [message.text for message in store.inbox()] == ["message 2"]  # gone from disk too
    agents.up.discard("chief")
    glance.run("  not sent")  # so not answered
    assert len(glance.inbox) == 1


def test_an_agent_that_isnt_running_is_shown_in_red_and_keeps_the_line(tmp_path: Path) -> None:
    agents = Agents("chief")
    glance = controller(tmp_path, agents)
    glance.open()
    shown = glance.preview(" move deep work to 3pm")
    assert (shown.note, shown.trouble) == ("assistant isn't running", True)
    glance.preview(" move deep work to 3pm!")
    assert agents.asked == 1  # herdr is asked once per open, not per key
    assert glance.run(" move deep work") == View(Lists(), problem="assistant isn't running")
    assert glance.preview("  hi").note == "chief"
    agents.up.add("assistant")
    glance.open()  # started since: the next open asks again
    assert not glance.preview(" hi").trouble


def test_a_line_that_means_something_else_by_enter_isnt_run(tmp_path: Path) -> None:
    """At 08:59 `9` is 09:00, but at 09:01 it's 21:00: Enter mustn't cut a block the preview
    didn't mean, even when the note reads the same."""
    plan = f"# Today {NOW.date().isoformat()}\n- 09:00-10:00 deep\n- 21:00-22:00 deep\n"
    (tmp_path / "tasks.md").write_text(plan, encoding="utf-8")
    clock = [NOW.replace(hour=8, minute=59)]
    glance = Controller(Store(tmp_path), CommandWords(), lambda: clock[0], Agents())
    glance.open()
    assert glance.preview("review 9 for 1h").note == "replaces deep"
    clock[0] = NOW.replace(hour=9, minute=1)
    view = glance.run("review 9 for 1h")
    assert view.message.startswith("it's 09:01 now, which changes what that does")
    assert glance.preview("review 9 for 1h").note == "replaces deep"
    assert glance.run("review 9 for 1h").message == "planned review 21:00-22:00 · replaces deep"
    clock[0] = NOW.replace(hour=23, minute=59)
    glance.preview("x 2pm for 1h")
    clock[0] += timedelta(minutes=2)  # tomorrow: a block then, not the one today it showed
    assert glance.run("x 2pm for 1h").message.startswith("it's 00:01 now")


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


def test_the_hud_sees_an_outside_change_but_a_typed_line_still_reloads_first(
    tmp_path: Path,
) -> None:
    glance = controller(tmp_path)
    glance.open()
    glance.run("new first")
    assert glance.saved() == Lists(Task("first"))
    (tmp_path / "tasks.md").write_text("# Active\n- from an agent\n", encoding="utf-8")
    assert glance.saved() == Lists(Task("from an agent"))
    assert glance.lists == Lists(Task("first"))  # what the overlay shows is left alone
    (tmp_path / "tasks.md").write_text("# Active\n- a\n- b\n", encoding="utf-8")
    assert glance.saved() == Lists(Task("from an agent"))  # unreadable: the last good lists
    assert glance.run("done").message == "tasks.md changed, run it again"


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
    glance.run("deep work 2pm for 1h")
    (slot,) = glance.day().slots
    assert (slot.number, slot.block.what, slot.start.hour) == (1, "deep work", 14)
    assert slot.end - slot.start == timedelta(hours=1)
