"""Agents running in herdr panes, talked to as if I'd typed into their pane.

`herdr agent get <name>` says whether one is running and ready, and `herdr agent prompt <name>
<text>` types a line into it. Nothing here raises: what goes wrong comes back as a sentence, and
a herdr that doesn't answer in time is one of those, so the overlay never waits long on it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from PySide6.QtCore import QProcess

SAID = {
    "agent_not_found": "{name} isn't running",
    "agent_blocked": "{name} is waiting on a question in its pane",
    "server_not_running": "herdr isn't running",
}
# herdr's failure is `{"error": {"code": "...", "message": "..."}}` on stderr; anything else it
# might say (a crash, a warning) is passed on as it is, so these are read with a pattern, not
# decoded as JSON, which would fail on them
CODE = re.compile(r'"code"\s*:\s*"([a-z_]+)"')
MESSAGE = re.compile(r'"message"\s*:\s*"((?:[^"\\]|\\.)*)"')
STATUS = re.compile(r'"agent_status"\s*:\s*"([a-z_]+)"')
ESCAPE = re.compile(r"\\(.)")


@dataclass(frozen=True)
class Herdr:
    """`command` runs herdr: its .exe, found once at start-up. Never a .cmd or .bat, which
    cmd.exe would run, reading a typed `&` or `%` as its own."""

    command: tuple[str, ...]
    check_s: float = 1.0  # runs on a key press, so it mustn't wait long
    send_s: float = 5.0

    def check(self, name: str) -> str:
        """ "" when it's running and ready for a line, else why not."""
        match self._run(self.check_s, "agent", "get", name):
            case _Answer(code=0, out=out) if _status(out) == "blocked":
                return SAID["agent_blocked"].format(name=name)
            case _Answer(code=0):
                return ""
            case _Answer(err=err, code=code):
                return _why(name, err, code)
            case _Gone(why=why):
                return why
            case _NoAnswer():
                return "herdr didn't answer"

    def send(self, name: str, text: str) -> str:
        """Types `text` into the agent's pane, marked as sent from glance, so the agent can tell
        it from what I type in its pane. A slash command (/compact) goes as it is, or it wouldn't
        run. "" when it's sent, else why not."""
        marked = text if text.startswith("/") else f"[via glance] {text}"
        match self._run(self.send_s, "agent", "prompt", name, marked):
            case _Answer(code=0):
                return ""
            case _Answer(err=err, code=code):
                return _why(name, err, code)
            case _Gone(why=why):
                return why
            case _NoAnswer():
                return f"herdr didn't answer: check {name}'s pane before sending it again"

    def _run(self, wait_s: float, *args: str) -> _Answer | _NoAnswer | _Gone:
        """Qt runs it: unlike Python's subprocess, failing to start and running out of time
        are values, not exceptions. herdr may not start because it's gone since start-up, or
        is half-way through an update. One that hasn't finished in time is stopped."""
        program, *before = self.command
        process = QProcess()
        process.start(program, [*before, *args])
        wait_ms = int(wait_s * 1000)
        if not process.waitForStarted(wait_ms):
            return _Gone("restart glance: herdr can't be run")
        if not process.waitForFinished(wait_ms):
            process.kill()
            process.waitForFinished(wait_ms)
            return _NoAnswer()
        out, err = process.readAllStandardOutput(), process.readAllStandardError()
        return _Answer(process.exitCode(), _text(out.data()), _text(err.data()))


@dataclass(frozen=True)
class NoHerdr:
    """herdr isn't installed, so no agent is running."""

    def check(self, name: str) -> str:
        return f"{name} isn't running: herdr isn't installed"

    def send(self, name: str, text: str) -> str:
        return self.check(name) if text else ""  # nothing to send isn't refused


@dataclass(frozen=True)
class _Answer:
    code: int
    out: str
    err: str


@dataclass(frozen=True)
class _NoAnswer:
    """It didn't finish in time: a line may have been sent anyway."""


@dataclass(frozen=True)
class _Gone:
    """herdr wasn't run at all, so nothing was sent."""

    why: str


def _text(raw: bytes | bytearray | memoryview) -> str:
    return bytes(raw).decode("utf-8", errors="replace")  # herdr writes UTF-8


def _status(out: str) -> str:
    return next((found[1] for found in STATUS.finditer(out)), "")


def _unescape(escape: re.Match[str]) -> str:
    """`\\n`, `\\t` and `\\r` are a space, as it's one line; `\\"` and `\\\\` the character."""
    return " " if escape[1] in "ntr" else escape[1]


def _why(name: str, err: str, code: int) -> str:
    """herdr's failure as one line: a known code says it plainly, else herdr's message (with
    JSON's `\\"` and `\\\\` undone), or what it wrote, or its exit code."""
    known = [SAID[found[1]].format(name=name) for found in CODE.finditer(err) if found[1] in SAID]
    said = [ESCAPE.sub(_unescape, found[1]) for found in MESSAGE.finditer(err)] or [err]
    line = " ".join(said[0].split())[:200]
    return next(iter(known), f"{name}: {line or f'herdr exited with {code}'}")
