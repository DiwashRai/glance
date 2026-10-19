from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import glance_cli
from app.core.model import CommandWords
from app.core.skill import skill

NOW = datetime(2026, 10, 19, 9, 58, 40, tzinfo=timezone(timedelta(hours=1)))


@pytest.fixture
def config(tmp_path: Path) -> Path:
    path = tmp_path / "config.toml"
    path.write_text('[glance]\ndata_folder = "data"\n', encoding="utf-8")
    return path


def glance(config: Path, *line: str) -> int:
    return glance_cli.run(["--config", str(config), *line], lambda: NOW)


def test_a_line_runs_as_if_typed_then_is_logged(
    config: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert glance(config, "fix", "the", "build") == 0  # the words, quoted or not
    assert glance_cli.run(["quick reply to Sam", "--config", str(config)], lambda: NOW) == 0
    assert glance(config, "--", "-1 on the RFC") == 0  # a line starting with -
    said = "started fix the build\nadded reply to Sam to quick\nstarted -1 on the RFC"
    assert capsys.readouterr().out == f"{said} · parked fix the build\n"
    data = config.parent / "data"
    assert (data / "tasks.md").read_text(encoding="utf-8").startswith("# Active\n- -1 on the RFC")
    assert (data / "events.log").read_text(encoding="utf-8").count("\n") == 4
    assert glance(config) == 0  # no line: the lists
    shown = capsys.readouterr().out
    assert shown.startswith("Active\n  -1 on the RFC\nFocus\n  nothing\n")
    assert "Quick\n  q1  reply to Sam\n" in shown
    assert glance(config, "--skill") == 0
    assert capsys.readouterr().out == f"{skill(CommandWords())}\n"


@pytest.mark.parametrize(
    ("line", "why"),
    [
        ("done q1", "there's no q1 in quick"),
        (" move deep work to 3pm", "lines for assistant aren't sent from the command line"),
    ],
)
def test_a_refused_line_says_why_and_changes_nothing(
    config: Path, capsys: pytest.CaptureFixture[str], line: str, why: str
) -> None:
    assert glance(config, line) == 1
    assert capsys.readouterr().err == f"{why}\n"
    assert not (config.parent / "data" / "tasks.md").exists()


@pytest.mark.parametrize(
    "argv",
    [
        ["--config", "missing.toml", "quick x"],  # never the defaults: they'd be the real lists
        ["quick", "x", "--skill"],
        ["-x"],
    ],
)
def test_a_mistyped_command_runs_nothing(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exited:
        glance_cli.run(argv, lambda: NOW)
    assert exited.value.code == 2


def test_a_file_it_cant_read_stops_everything(
    config: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = config.parent / "data"
    data.mkdir()
    (data / "tasks.md").write_text("# Active\n- a\n- b\n", encoding="utf-8")
    for line in ((), ("new c",)):  # the lists too: they'd be wrong
        assert glance(config, *line) == 1
        assert capsys.readouterr().err.startswith("tasks.md line 3: only one task can be active")
