from pathlib import Path

import msgspec
import pytest

from app.config import load_settings
from app.core.model import CommandWords


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_a_missing_file_uses_the_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    settings = load_settings(tmp_path / "missing.toml")
    assert settings.data_folder == tmp_path / "local" / "glance"
    assert settings.words == CommandWords()


def test_reads_glance_and_leaves_the_collectors_tables_alone(tmp_path: Path) -> None:
    text = """\
[updater]
output_path = "data/status.json"

[glance]
data_folder = "data"

[glance.commands]
park = ["Park", "Later"]
"""
    settings = load_settings(write(tmp_path, text))
    assert settings.data_folder == tmp_path / "data"
    assert settings.words.park == ("park", "later")
    assert settings.words.new == CommandWords().new


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ('[glance.commands]\npark = "park"\n', "$.glance.commands.park"),
        ('[glance.commands]\npark = ["two words"]\n', "$.glance.commands.park"),
        ('[glance.commands]\nnew = ["x\\n"]\n', "$.glance.commands.new"),
        ("[glance]\ndata_dir = 'x'\n", "data_dir"),
        ('[glance.commands]\npark = ["park", "S"]\n', "'s' is used by both park and switch"),
    ],
)
def test_bad_values_name_the_problem(tmp_path: Path, text: str, error: str) -> None:
    with pytest.raises(msgspec.ValidationError) as raised:
        load_settings(write(tmp_path, text))
    assert error in str(raised.value)
