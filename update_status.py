import argparse
import logging
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import cast

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from app.providers.registry import provider_registry
from app.status_format import format_status_payload
from app.types import ProviderContext, StatusFile, StatusFileRow, TomlTable

DEFAULT_CONFIG_PATH = "config.local.toml"
LOG_DIR = Path("logs")
ALL_LOG_PATH = LOG_DIR / "update_status.log"
ERROR_LOG_PATH = LOG_DIR / "update_status.error.log"

logger = logging.getLogger("update_status")


@dataclass(slots=True)
class CliArgs:
    config: Path
    output: Path | None = None
    dry_run: bool = False


@dataclass(slots=True)
class Thresholds:
    low: int
    medium: int
    high: int


@dataclass(slots=True)
class UpdaterConfig:
    output_path: Path = Path("data/status.local.json")


@dataclass(slots=True)
class EntryConfig:
    provider: str
    label: str
    icon: str
    thresholds: Thresholds
    requests: list[TomlTable]


@dataclass(slots=True)
class AppTomlConfig:
    updater: UpdaterConfig = field(default_factory=UpdaterConfig)
    providers: dict[str, TomlTable] = field(default_factory=dict)  # pyright: ignore[reportUnknownVariableType]
    entries: list[EntryConfig] = field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]


def parse_args(argv: Sequence[str] | None = None) -> CliArgs:
    parser = argparse.ArgumentParser(
        description="Collect provider counts and build a Glance status payload."
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        help="Path to write status.json. Overrides config.toml when provided.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the status payload instead of writing it to disk.",
    )
    ns = parser.parse_args(argv)
    return CliArgs(config=ns.config, output=ns.output, dry_run=ns.dry_run)


def load_config(config_path: Path) -> AppTomlConfig:
    if not config_path.exists():
        return AppTomlConfig()

    with config_path.open("rb") as f:
        raw = tomllib.load(f)

    return parse_toml_config(raw)


def configure_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    all_file_handler = RotatingFileHandler(
        ALL_LOG_PATH,
        maxBytes=1_000_000,
        backupCount=1,
        encoding="utf-8",
    )
    all_file_handler.setLevel(logging.INFO)
    all_file_handler.setFormatter(formatter)

    error_file_handler = RotatingFileHandler(
        ERROR_LOG_PATH,
        maxBytes=1_000_000,
        backupCount=1,
        encoding="utf-8",
    )
    error_file_handler.setLevel(logging.ERROR)
    error_file_handler.setFormatter(formatter)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(all_file_handler)
    root_logger.addHandler(error_file_handler)


def parse_toml_config(raw: dict[str, object]) -> AppTomlConfig:
    updater_raw = get_table(raw, "updater")
    providers_raw = get_table(raw, "providers")
    entries_raw = get_entries(raw)

    output_path = updater_raw.get("output_path", "data/status.local.json")
    if not isinstance(output_path, str):
        raise ValueError("[updater].output_path must be a string")

    providers: dict[str, TomlTable] = {}
    for name, value in providers_raw.items():
        if not isinstance(value, dict):
            raise ValueError(f"[providers.{name}] must be a TOML table")
        providers[name] = value

    entries = [parse_entry(entry, i) for i, entry in enumerate(entries_raw)]

    return AppTomlConfig(
        updater=UpdaterConfig(output_path=Path(output_path)),
        providers=providers,
        entries=entries,
    )


def parse_entry(raw: dict[str, object], index: int) -> EntryConfig:
    provider = raw.get("provider")
    label = raw.get("label")
    icon = raw.get("icon")
    thresholds = raw.get("thresholds", {})
    requests = raw.get("requests", [])

    if not isinstance(provider, str) or not provider:
        raise ValueError(f"entries[{index}].provider must be a non-empty string")

    if not isinstance(label, str) or not label:
        raise ValueError(f"entries[{index}].label must be a non-empty string")

    if not isinstance(icon, str):
        raise ValueError(f"entries[{index}].icon must be a string")

    if not isinstance(thresholds, dict):
        raise ValueError(f"entries[{index}].thresholds must be a table")
    thresholds = cast(dict[str, object], thresholds)

    if not isinstance(requests, list):
        raise ValueError(f"entries[{index}].requests must be a list")
    requests = cast(list[object], requests)

    parsed_requests: list[TomlTable] = []
    for j, request in enumerate(requests):
        if not isinstance(request, dict):
            raise ValueError(f"entries[{index}].requests[{j}] must be a TOML table")
        parsed_requests.append(cast(TomlTable, request))

    return EntryConfig(
        provider=provider,
        label=label,
        icon=icon,
        thresholds=parse_thresholds(thresholds),
        requests=parsed_requests,
    )


def parse_thresholds(raw: dict[str, object]) -> Thresholds:
    low = raw.get("low")
    medium = raw.get("medium")
    high = raw.get("high")

    if not isinstance(low, int):
        raise ValueError("entry.thresholds.low must be an int")
    if not isinstance(medium, int):
        raise ValueError("entry.thresholds.medium must be an int")
    if not isinstance(high, int):
        raise ValueError("entry.thresholds.high must be an int")

    return Thresholds(low=low, medium=medium, high=high)


def get_table(config: dict[str, object], name: str) -> dict[str, object]:
    table = config.get(name, {})
    if not isinstance(table, dict):
        raise ValueError(f"[{name}] must be a TOML table")
    return cast(dict[str, object], table)


def get_entries(config: dict[str, object]) -> list[dict[str, object]]:
    entries = config.get("entries", [])
    if not isinstance(entries, list):
        raise ValueError("[[entries]] must be declared as an array of tables")

    entries = cast(list[object], entries)
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"entries[{i}] must be a TOML table")
    return cast(list[dict[str, object]], entries)


def get_provider_kind(config: AppTomlConfig, provider_name: str):
    provider = config.providers.get(provider_name)
    if not isinstance(provider, dict):
        raise ValueError(f"[providers.{provider_name}] must be a TOML table")

    kind = provider.get("kind")
    if not isinstance(kind, str) or not kind:
        raise ValueError(f"[providers.{provider_name}].kind must be a non-empty string")

    return kind


def get_severity(count: int, thresholds: Thresholds) -> int:
    if count < thresholds.low:
        return 0
    if count < thresholds.medium:
        return 1
    if count < thresholds.high:
        return 2
    return 3


def run_request(
    kind: str, provider_name: str, config: AppTomlConfig, requests: list[TomlTable]
) -> int:
    provider = provider_registry.create(kind)
    return provider.count(
        ProviderContext(
            provider_name=provider_name,
            provider_config=config.providers[provider_name],
            requests=requests,
        )
    )


def build_status_rows(config: AppTomlConfig) -> list[StatusFileRow]:
    rows: list[StatusFileRow] = []
    for entry in config.entries:
        provider_start = time.perf_counter()
        logger.info("Starting provider '%s' for '%s'", entry.provider, entry.label)
        try:
            provider_kind = get_provider_kind(config, entry.provider)
            total = run_request(provider_kind, entry.provider, config, entry.requests)
            logger.info(
                "Finished provider '%s' for '%s' in %.3fs",
                entry.provider,
                entry.label,
                time.perf_counter() - provider_start,
            )
            rows.append((entry.label, entry.icon, total, get_severity(total, entry.thresholds)))
        except Exception as exc:
            logger.error(
                "Failed to update '%s' from provider '%s': %s",
                entry.label,
                entry.provider,
                exc,
            )
            logger.exception(
                "Traceback for provider failure on '%s' from provider '%s'",
                entry.label,
                entry.provider,
            )
            logger.info(
                "Provider '%s' for '%s' failed after %.3fs",
                entry.provider,
                entry.label,
                time.perf_counter() - provider_start,
            )
            rows.append((entry.label, entry.icon, -1, 3))

    return rows


def build_status_payload(config: AppTomlConfig) -> StatusFile:
    return {"f": build_status_rows(config)}


def publish_status_output(content: str, output_path: Path):
    if output_path.exists() and output_path.read_text(encoding="utf-8") == content:
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")


def main(argv: Sequence[str] | None = None):
    configure_logging()
    run_start = time.perf_counter()
    logger.info("Starting update_status run")
    args = parse_args(argv)
    config = load_config(args.config)
    payload = build_status_payload(config)
    content = format_status_payload(payload)

    if args.dry_run:
        print(content, end="")
        logger.info("Finished update_status run in %.3fs", time.perf_counter() - run_start)
        return 0

    publish_status_output(content, config.updater.output_path)
    logger.info("Finished update_status run in %.3fs", time.perf_counter() - run_start)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
