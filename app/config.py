"""Glance's settings, read once from the `[glance]` table of the TOML config file. config.toml
lists every key, commented out, with its default.

The counts the HUD shows come from where the collector writes them: `[updater].output_path`.

Every key has a default, and a missing file means all defaults. msgspec does the checking: any
bad or unknown value under `[glance]` raises `msgspec.ValidationError` naming the key. The other
tables in the file belong to the collector (`update_status.py`).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

import msgspec

from app.core.model import CommandWords, HudSettings

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

DEFAULT_WORDS = CommandWords()
Word = Annotated[str, msgspec.Meta(pattern=r"^\S+\Z")]
Words = Annotated[tuple[Word, ...], msgspec.Meta(min_length=1)]


class _Commands(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    new: Words = DEFAULT_WORDS.new
    park: Words = DEFAULT_WORDS.park
    wait: Words = DEFAULT_WORDS.wait
    switch: Words = DEFAULT_WORDS.switch
    done: Words = DEFAULT_WORDS.done
    focus: Words = DEFAULT_WORDS.focus
    unfocus: Words = DEFAULT_WORDS.unfocus
    quick: Words = DEFAULT_WORDS.quick
    step: Words = DEFAULT_WORDS.step
    skip: Words = DEFAULT_WORDS.skip
    finish: Words = DEFAULT_WORDS.finish
    unblock: Words = DEFAULT_WORDS.unblock

    def groups(self) -> dict[str, tuple[str, ...]]:
        """Each command's words, lower-cased."""
        named: dict[str, tuple[str, ...]] = msgspec.structs.asdict(self)
        return {command: tuple(word.lower() for word in words) for command, words in named.items()}

    def __post_init__(self) -> None:
        """msgspec reports a ValueError raised here as a ValidationError, like any other."""
        owner: dict[str, str] = {}
        for command, words in self.groups().items():
            for word in words:
                first = owner.setdefault(word, command)
                if first != command:
                    raise ValueError(f"'{word}' is used by both {first} and {command}")


class _Hud(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    look: Literal["native", "box"] = "native"
    labels: Literal["icons", "text"] = "icons"
    show_active: bool = True


class _Glance(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    data_folder: str = ""
    commands: _Commands = msgspec.field(default_factory=_Commands)
    hud: _Hud = msgspec.field(default_factory=_Hud)


class _Updater(msgspec.Struct, frozen=True):
    """The collector's table: glance only reads where it writes the counts."""

    output_path: str = "data/status.local.json"


class _File(msgspec.Struct, frozen=True):
    glance: _Glance = msgspec.field(default_factory=_Glance)
    updater: _Updater = msgspec.field(default_factory=_Updater)


@dataclass(frozen=True)
class Settings:
    data_folder: Path
    words: CommandWords
    hud: HudSettings
    counts_file: Path


def default_config(home: Path) -> Path:
    """config.local.toml in `home` if it exists, else config.toml. The collector uses the same
    rule, so both read the same settings."""
    local = home / "config.local.toml"
    return local if local.exists() else home / "config.toml"


def load_settings(path: Path) -> Settings:
    text = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    file = msgspec.convert(tomllib.loads(text), _File)
    glance = file.glance
    return Settings(
        data_folder=_data_folder(glance.data_folder, path.parent),
        words=CommandWords(**glance.commands.groups()),
        hud=HudSettings(**msgspec.structs.asdict(glance.hud)),
        counts_file=path.parent / file.updater.output_path,
    )


def _data_folder(value: str, config_folder: Path) -> Path:
    """Empty means %LOCALAPPDATA%\\glance. A relative path is relative to the config file."""
    if not value:
        return Path(os.environ["LOCALAPPDATA"]) / "glance"
    folder = Path(value).expanduser()
    return folder if folder.is_absolute() else config_folder / folder
