import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeAlias, cast

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from app.providers.dummy import get_dummy_count
from app.providers.github_gh import get_gh_pr_count
from app.providers.jira import get_issue_count
from app.providers.outlook_emails import get_unread_email_count
from app.providers.todoist import DEFAULT_FILTER, get_task_count
from app.status_format import format_status_payload
from app.types import ProviderFunction, StatusFile, StatusFileRow

DEFAULT_CONFIG_PATH = "config.local.toml"
PROVIDER_FUNCTIONS: dict[str, ProviderFunction] = {
    "dummy": get_dummy_count,
    "github-gh": get_gh_pr_count,
    "jira": get_issue_count,
    "outlook": get_unread_email_count,
    "todoist": get_task_count,
}


@dataclass(slots=True)
class CliArgs:
    config: Path
    output: Path | None = None
    dry_run: bool = False


TomlValue: TypeAlias = str | int | float | bool | list["TomlValue"] | dict[str, "TomlValue"]


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
    requests: list[dict[str, TomlValue]]


@dataclass(slots=True)
class AppTomlConfig:
    updater: UpdaterConfig = field(default_factory=UpdaterConfig)
    providers: dict[str, dict[str, TomlValue]] = field(default_factory=dict)  # pyright: ignore[reportUnknownVariableType]
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


def parse_toml_config(raw: dict[str, object]) -> AppTomlConfig:
    updater_raw = get_table(raw, "updater")
    providers_raw = get_table(raw, "providers")
    entries_raw = get_entries(raw)

    output_path = updater_raw.get("output_path", "data/status.local.json")
    if not isinstance(output_path, str):
        raise ValueError("[updater].output_path must be a string")

    providers: dict[str, dict[str, TomlValue]] = {}
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

    parsed_requests: list[dict[str, TomlValue]] = []
    for j, request in enumerate(requests):
        if not isinstance(request, dict):
            raise ValueError(f"entries[{index}].requests[{j}] must be a TOML table")
        parsed_requests.append(cast(dict[str, TomlValue], request))

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


def run_outlook_request(
    fetcher: ProviderFunction,
    provider_name: str,
    config: AppTomlConfig,
    request: dict[str, TomlValue],
) -> int:
    provider = config.providers[provider_name]
    outlook_store = provider["outlook_store"]
    if not isinstance(outlook_store, str) or not outlook_store:
        raise ValueError(
            f"[providers.{provider_name}].outlook_store must be a non-empty string when provided"
        )
    outlook_store = outlook_store.lower()

    folders = request.get("folders")
    if not isinstance(folders, list) or not folders:
        raise ValueError("Outlook requests require a non-empty 'folders' list")

    folder_list: list[int | str] = []
    for folder in folders:
        if not isinstance(folder, str) or not folder:
            raise ValueError("Outlook folder list items must be non-empty strings")
        if folder.isdigit():
            folder_list.append(int(folder))
        else:
            folder_list.append(folder)

    if not folder_list:
        raise ValueError("Outlook requests require at least one folder in 'folders'")

    return fetcher(folder_list, outlook_store=outlook_store)


def run_jira_request(
    fetcher: ProviderFunction,
    provider_name: str,
    config: AppTomlConfig,
    request: dict[str, TomlValue],
) -> int:
    provider = config.providers[provider_name]
    base_url = provider["base_url"]
    if not isinstance(base_url, str) or not base_url:
        raise ValueError(f"[providers.{provider_name}].base_url must be a non-empty string")

    api_version = provider.get("api_version")
    if not isinstance(api_version, (int, str)) or not str(api_version):
        raise ValueError(f"[providers.{provider_name}].api_version must be set")

    api_token = provider.get("api_token")
    if not isinstance(api_token, str) or not api_token:
        raise ValueError(f"[providers.{provider_name}].api_token must be a non-empty string")

    jql = request.get("jql")
    if not isinstance(jql, list) or not jql:
        raise ValueError("Jira requests require a non-empty 'jql' list")

    jqls: list[str] = []
    for item in jql:
        if not isinstance(item, str) or not item:
            raise ValueError("Jira jql items must be non-empty strings")
        jqls.append(item)

    return fetcher(base_url, api_version, api_token, jqls)


def run_github_gh_request(fetcher: ProviderFunction, request: dict[str, TomlValue]) -> int:
    args = request.get("args")
    if not isinstance(args, list) or not args:
        raise ValueError("GitHub requests require a non-empty 'args' list")
    return fetcher([args])


def run_todoist_request(
    fetcher: ProviderFunction,
    provider_name: str,
    config: AppTomlConfig,
    request: dict[str, TomlValue],
) -> int:
    provider = config.providers[provider_name]
    api_token = provider["api_token"]
    if not isinstance(api_token, str) or not api_token:
        raise ValueError(f"[providers.{provider_name}].api_token must be a non-empty string")

    filter_value = request.get("filter")
    if filter_value is None:
        filter_value = request.get("query", DEFAULT_FILTER)
    if not isinstance(filter_value, str) or not filter_value:
        raise ValueError("Todoist requests require 'filter' to be a non-empty string")

    lang = request.get("lang")
    if lang is not None and (not isinstance(lang, str) or not lang):
        raise ValueError("Todoist request 'lang' must be a non-empty string when provided")

    return fetcher(api_token, filter_value=filter_value, lang=lang)


def run_dummy_request(
    fetcher: ProviderFunction, config: AppTomlConfig, request: dict[str, TomlValue]
) -> int:
    key = request["key"]
    if not isinstance(key, str) or not key:
        raise ValueError("Dummy requests require a non-empty 'key' string")
    start = request["start"]
    step = request["step"]
    if not isinstance(start, int) or not isinstance(step, int):
        raise ValueError("Dummy requests require 'start' and 'step' to be ints")
    return fetcher(config.updater.output_path, key, start, step)


def run_request(
    kind: str, provider_name: str, config: AppTomlConfig, request: dict[str, TomlValue]
) -> int:
    fetcher = PROVIDER_FUNCTIONS[kind]
    request_count = 0
    if kind == "outlook":
        request_count = run_outlook_request(fetcher, provider_name, config, request)

    if kind == "jira":
        request_count = run_jira_request(fetcher, provider_name, config, request)

    if kind == "github-gh":
        request_count = run_github_gh_request(fetcher, request)

    if kind == "todoist":
        request_count = run_todoist_request(fetcher, provider_name, config, request)

    if kind == "dummy":
        request_count = run_dummy_request(fetcher, config, request)

    return request_count


def build_status_rows(config: AppTomlConfig) -> list[StatusFileRow]:
    rows: list[StatusFileRow] = []
    for entry in config.entries:
        provider_kind = get_provider_kind(config, entry.provider)
        total = 0
        total = sum(
            run_request(provider_kind, entry.provider, config, request)
            for request in entry.requests
        )
        rows.append((entry.label, entry.icon, total, get_severity(total, entry.thresholds)))

    return rows


def build_status_payload(config: AppTomlConfig) -> StatusFile:
    return {"f": build_status_rows(config)}


def publish_status_output(content: str, output_path: Path):
    if output_path.exists() and output_path.read_text(encoding="utf-8") == content:
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")


def main(argv: Sequence[str] | None = None):
    args = parse_args(argv)
    config = load_config(args.config)
    payload = build_status_payload(config)
    content = format_status_payload(payload)

    if args.dry_run:
        print(content, end="")
        return 0

    publish_status_output(content, config.updater.output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
