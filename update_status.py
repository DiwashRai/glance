"""The collector: asks each entry's provider for its count, then writes the counts the HUD shows
to `[updater].output_path`. An entry whose provider fails is written as -1, so the others still
show."""

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path

import msgspec

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from app.config import Updater, default_config
from app.providers import COUNTS
from app.types import CountsRow, NonEmpty, Table

LOG_DIR = Path("logs")

logger = logging.getLogger("update_status")


class Thresholds(msgspec.Struct, frozen=True):
    low: int
    medium: int
    high: int


class Entry(msgspec.Struct, frozen=True):
    provider: NonEmpty  # a name under [providers]
    label: NonEmpty
    icon: str
    thresholds: Thresholds
    requests: tuple[Table, ...] = ()  # checked by the provider


class Collector(msgspec.Struct, frozen=True):
    """The collector's tables in the config file. `[glance]` is glance's, so it's skipped."""

    updater: Updater = msgspec.field(default_factory=Updater)
    providers: dict[str, Table] = {}
    entries: tuple[Entry, ...] = ()


class _Kind(msgspec.Struct):
    kind: NonEmpty  # which provider a [providers.<name>] table is for


@dataclass(frozen=True)
class CliArgs:
    config: Path
    dry_run: bool


def parse_args() -> CliArgs:
    parser = argparse.ArgumentParser(
        description="Collect provider counts and build a Glance status payload."
    )
    home = Path(__file__).resolve().parent
    parser.add_argument("--config", default=default_config(home), type=Path)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the status payload instead of writing it to disk.",
    )
    ns = parser.parse_args()
    return CliArgs(config=ns.config, dry_run=ns.dry_run)


def load_config(path: Path) -> Collector:
    """A missing file means nothing to collect. msgspec does the checking, naming the key."""
    text = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    return msgspec.convert(tomllib.loads(text), Collector)


def configure_logging() -> None:
    """Everything to the console and update_status.log, and errors to their own log too."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    errors = _rotating("update_status.error.log")
    errors.setLevel(logging.ERROR)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=[logging.StreamHandler(), _rotating("update_status.log"), errors],
        force=True,
    )


def _rotating(name: str) -> RotatingFileHandler:
    return RotatingFileHandler(LOG_DIR / name, maxBytes=1_000_000, backupCount=1, encoding="utf-8")


def get_severity(count: int, thresholds: Thresholds) -> int:
    if count < thresholds.low:
        return 0
    if count < thresholds.medium:
        return 1
    if count < thresholds.high:
        return 2
    return 3


def build_status_rows(config: Collector) -> list[CountsRow]:
    rows: list[CountsRow] = []
    for entry in config.entries:
        provider_start = time.perf_counter()
        logger.info("Starting provider '%s' for '%s'", entry.provider, entry.label)
        try:
            provider = config.providers[entry.provider]
            count = COUNTS[msgspec.convert(provider, _Kind).kind]
            total = count(provider, entry.requests)
            logger.info(
                "Finished provider '%s' for '%s' in %.3fs",
                entry.provider,
                entry.label,
                time.perf_counter() - provider_start,
            )
            rows.append((entry.label, entry.icon, total, get_severity(total, entry.thresholds)))
        except Exception as exc:
            logger.exception(
                "Failed to update '%s' from provider '%s': %s",
                entry.label,
                entry.provider,
                exc,
            )
            logger.info(
                "Provider '%s' for '%s' failed after %.3fs",
                entry.provider,
                entry.label,
                time.perf_counter() - provider_start,
            )
            rows.append((entry.label, entry.icon, -1, 3))

    return rows


def counts_json(rows: list[CountsRow]) -> str:
    """`{"f": [...]}`, a row to a line."""
    body = ",\n".join(f"    {json.dumps(row, ensure_ascii=False)}" for row in rows)
    return '{\n  "f": [\n' + (f"{body}\n" if body else "") + "  ]\n}\n"


def publish_status_output(content: str, output_path: Path):
    if output_path.exists() and output_path.read_text(encoding="utf-8") == content:
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp = output_path.with_name(f"{output_path.name}.tmp")
    temp.write_text(content, encoding="utf-8")
    os.replace(temp, output_path)  # atomic, so the HUD never reads half a file


def main():
    configure_logging()
    run_start = time.perf_counter()
    logger.info("Starting update_status run")
    args = parse_args()
    config = load_config(args.config)
    content = counts_json(build_status_rows(config))

    if args.dry_run:
        print(content, end="")
    else:
        # relative to the config file, as glance resolves it, so both find the same file
        publish_status_output(content, args.config.parent / config.updater.output_path)
    logger.info("Finished update_status run in %.3fs", time.perf_counter() - run_start)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
