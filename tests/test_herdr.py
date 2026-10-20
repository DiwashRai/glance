"""The edge to herdr, with a fake herdr: a Python script that answers the way herdr would."""

import json
import sys
from pathlib import Path

import pytest

from app.herdr import Herdr, NoHerdr


def fake(folder: Path, out: str = "", err: str = "", code: int = 0) -> Herdr:
    """A herdr that doesn't answer in time isn't tested here: that needs the real clock."""
    script = folder / "herdr.py"
    lines = ["import sys", f"sys.stdout.write({out!r})", f"sys.stderr.write({err!r})"]
    script.write_text("\n".join([*lines, f"sys.exit({code})"]), encoding="utf-8")
    return Herdr((sys.executable, str(script)), check_s=10, send_s=10)


def failed(code: str, message: str) -> str:
    """herdr's failure: its JSON on stderr, with exit code 1."""
    return json.dumps({"error": {"code": code, "message": message}})


def status(state: str) -> str:
    return json.dumps({"result": {"agent": {"agent_status": state}}})


@pytest.mark.parametrize(
    ("answer", "said"),
    [
        ({"out": status("idle")}, ""),
        ({"err": failed("agent_not_found", "x"), "code": 1}, "chief isn't running"),
        ({"out": status("blocked")}, "chief is waiting on a question in its pane"),
        # an unknown code: herdr's message, as one line, with JSON's escapes undone
        (
            {"err": failed("new_code", 'no {socket} at "C:\\h"\nrun herdr'), "code": 1},
            'chief: no {socket} at "C:\\h" run herdr',
        ),
        ({"err": "it crashed\n", "code": 3}, "chief: it crashed"),  # not herdr's JSON: as it is
        ({"code": 3}, "chief: herdr exited with 3"),
    ],
)
def test_herdrs_answer_becomes_a_sentence_never_an_error(
    tmp_path: Path, answer: dict[str, str | int], said: str
) -> None:
    herdr = fake(
        tmp_path, str(answer.get("out", "")), str(answer.get("err", "")), int(answer.get("code", 0))
    )
    assert herdr.check("chief") == said


def test_a_line_is_marked_as_from_glance_but_a_slash_command_isnt(tmp_path: Path) -> None:
    script = tmp_path / "herdr.py"
    typed = tmp_path / "typed.txt"
    script.write_text(f"import sys\nopen({str(typed)!r}, 'a').write(sys.argv[-1] + '\\n')")
    herdr = Herdr((sys.executable, str(script)), check_s=10, send_s=10)
    assert herdr.send("chief", "move deep work") == ""
    assert herdr.send("chief", "/compact") == ""
    assert typed.read_text().splitlines() == ["[via glance] move deep work", "/compact"]


def test_a_herdr_that_cant_be_run_is_said_so(tmp_path: Path) -> None:
    """Gone since start-up, or half-way through an update."""
    broken = tmp_path / "broken.exe"
    broken.write_bytes(b"")
    for program in (tmp_path / "gone.exe", broken):
        assert (
            Herdr((str(program),))
            .send("chief", "hi")
            .startswith("restart glance: herdr can't be run")
        )
    assert NoHerdr().send("chief", "hi") == "chief isn't running: herdr isn't installed"
