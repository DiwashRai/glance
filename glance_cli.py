"""glance on the command line, for the owner's agents (and the owner). Usage:

    glance                       the lists, numbered the way commands count them
    glance '<line>'              runs a line as if it were typed into the overlay
    glance --from NAME '<text>'  leaves the owner a message, shown until they clear it
    glance --skill               how to use it, for an agent
    glance --config PATH         another config file, before or after any of those

It goes through the same controller as the overlay: the same checks, saved to tasks.md and
logged to events.log the same way. It runs beside the app, which notices the change.
"""

from __future__ import annotations

import argparse
import io
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from app.config import default_config, load_settings
from app.controller import Controller
from app.core.listing import listing
from app.core.skill import skill
from app.store import Store

HOME = Path(__file__).resolve().parent  # where config.toml is
MESSAGE_MOST = 300  # characters: a few lines in the overlay


def main() -> int:
    # UTF-8 whatever the code page, as a title can hold any character: a console shows it right,
    # and so does an agent reading the output, where cp1252 couldn't print an emoji at all
    for stream in (sys.stdout, sys.stderr):
        cast("io.TextIOWrapper", stream).reconfigure(encoding="utf-8")
    return run(sys.argv[1:], _now)


def run(argv: list[str], now: Callable[[], datetime]) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    config: str = args.config
    line = " ".join(args.line)
    if config and not Path(config).is_file():  # not the defaults: they'd be the real lists
        parser.error(f"there's no config file at {config}")
    if args.skill and line:
        parser.error("--skill takes no line")
    settings = load_settings(Path(config) if config else default_config(HOME))
    if args.skill:
        print(skill(settings.words))
        return 0
    if args.sender:
        return _tell(Store(settings.data_folder), args.sender, line, now())
    controller = Controller(Store(settings.data_folder), settings.words, now, _NotSent())
    opened = controller.open()
    if opened.problem:
        print(opened.problem, file=sys.stderr)
        return 1
    if not line.strip():
        print(listing(opened.lists, now().date()))
        return 0
    view = controller.run(line)
    if not view.accepted:
        print(view.problem or view.message, file=sys.stderr)
        return 1
    print(view.message)
    controller.write_history()
    return 0


def _tell(store: Store, sender: str, line: str, at: datetime) -> int:
    """One line, so it fits the overlay's message card."""
    text = " ".join(line.split())
    if not text or len(text) > MESSAGE_MOST:
        too_long = f"is {MESSAGE_MOST} characters at most: put more in a file and give its path"
        print(f"a message {too_long if text else 'needs some text'}", file=sys.stderr)
        return 1
    store.tell(sender, text, at)
    print("left for the owner in glance")
    return 0


def _parser() -> argparse.ArgumentParser:
    """Options go before or after the line, not inside it; a line that starts with - goes
    after --."""
    parser = argparse.ArgumentParser(
        prog="glance",
        description="With no line, the lists; with one, it runs as if typed into glance.",
        epilog="For an agent: glance --skill",
    )
    parser.add_argument("--config", default="", help="default: config.local.toml or config.toml")
    parser.add_argument("--skill", action="store_true", help="how to use glance, for an agent")
    parser.add_argument(
        "--from",
        dest="sender",
        type=_name,
        metavar="NAME",
        help="the line is a message for the owner, from you",
    )
    parser.add_argument("line", nargs="*", help="a line, as typed into glance")
    return parser


def _name(text: str) -> str:
    """Who a message is from. Never blank: a blank one would run the message as a line."""
    if not text.strip():
        raise argparse.ArgumentTypeError("give your name, like chief")
    return text.strip()


class _NotSent:
    """A line for an agent (spaces first) isn't sent from here: agents have their own ways."""

    def check(self, name: str) -> str:
        return f"lines for {name} aren't sent from the command line"

    def send(self, name: str, text: str) -> str:
        return self.check(name) if text else ""


def _now() -> datetime:
    """Local time with its UTC offset, as the app reads it."""
    return datetime.now(UTC).astimezone()


if __name__ == "__main__":
    raise SystemExit(main())
