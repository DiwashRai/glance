import argparse
import json
import tomllib
from pathlib import Path

from providers.github_gh import get_search_result_count
from providers.jira import get_issue_count
from providers.outlook_emails import get_unread_email_count


DEFAULT_CONFIG_PATH = "config.toml"
PROVIDER_FUNCTIONS = {
    "github-gh": get_search_result_count,
    "jira": get_issue_count,
    "outlook": get_unread_email_count,
}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Collect provider counts and build a Glance status payload."
    )
    parser.add_argument(
        "--output",
        help="Path to write status.json. Overrides config.toml when provided.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the status payload instead of writing it to disk.",
    )
    return parser.parse_args(argv)


def load_config(config_path=DEFAULT_CONFIG_PATH):
    with open(config_path, "rb") as f:
        return tomllib.load(f)


def get_table(config, name):
    value = config.get(name, {})
    if not isinstance(value, dict):
        raise ValueError(f"[{name}] must be a TOML table")
    return value


def get_entries(config):
    entries = config.get("entries", [])
    if not isinstance(entries, list):
        raise ValueError("[[entries]] must be declared as an array of tables")
    return entries


def resolve_output_path(config, cli_output_path):
    if cli_output_path:
        return cli_output_path

    updater = get_table(config, "updater")
    output_path = updater.get("output_path")
    if output_path is not None:
        return str(output_path)

    glance = get_table(config, "glance")
    output_path = glance.get("path")
    if output_path:
        return str(output_path)

    raise ValueError(
        "Output path missing. Set --output, [updater].output_path, or [glance].path"
    )


def get_provider_kind(config, provider_name):
    providers = get_table(config, "providers")
    provider = providers.get(provider_name)
    if not isinstance(provider, dict):
        raise ValueError(f"[providers.{provider_name}] must be a TOML table")

    kind = provider.get("kind")
    if not isinstance(kind, str) or not kind:
        raise ValueError(f"[providers.{provider_name}].kind must be a non-empty string")

    return kind


def get_thresholds(entry):
    thresholds = entry.get("thresholds", {})
    if not isinstance(thresholds, dict):
        raise ValueError("[[entries]].thresholds must be an inline TOML table")

    required_keys = ("low", "medium", "high")
    values = []
    for key in required_keys:
        if key not in thresholds:
            raise ValueError(f"[[entries]].thresholds.{key} is required")
        values.append(int(thresholds[key]))

    low, medium, high = values
    if not (low <= medium <= high):
        raise ValueError("Thresholds must satisfy low <= medium <= high")

    return low, medium, high


def get_requests(entry):
    requests = entry.get("requests", [])
    if not isinstance(requests, list) or not requests:
        raise ValueError("[[entries]].requests must be a non-empty list")

    normalized = []
    for request in requests:
        if not isinstance(request, dict):
            raise ValueError("Each [[entries]].requests item must be a TOML inline table")
        normalized.append(request)
    return normalized


def get_severity(count, thresholds):
    low, medium, high = thresholds
    if count < low:
        return 0
    if count < medium:
        return 1
    if count < high:
        return 2
    return 3


def run_request(kind, request):
    fetcher = PROVIDER_FUNCTIONS.get(kind)
    if fetcher is None:
        raise ValueError(f"Unsupported provider kind: {kind}")

    if kind == "outlook":
        folders = request.get("folders")
        if folders is None:
            folder = request.get("folder")
            if not isinstance(folder, str) or not folder:
                raise ValueError(
                    "Outlook requests require a non-empty 'folder' or 'folders'"
                )
            folders = [folder]
        if not isinstance(folders, list) or not folders:
            raise ValueError("Outlook requests require a non-empty 'folders' list")
        if not all(isinstance(folder, str) and folder for folder in folders):
            raise ValueError("Outlook 'folders' entries must all be non-empty strings")
        return fetcher(folders)

    if kind == "jira":
        jql = request.get("jql")
        if not isinstance(jql, str) or not jql:
            raise ValueError("Jira requests require a non-empty 'jql'")
        return fetcher(jql)

    if kind == "github-gh":
        search = request.get("search")
        if not isinstance(search, str) or not search:
            raise ValueError("GitHub requests require a non-empty 'search'")
        return fetcher(search)

    raise ValueError(f"Unsupported provider kind: {kind}")


def build_status_rows(config):
    rows = []
    for entry in get_entries(config):
        provider_name = entry.get("provider")
        label = entry.get("label")
        icon = entry.get("icon")

        if not isinstance(provider_name, str) or not provider_name:
            raise ValueError("[[entries]].provider must be a non-empty string")
        if not isinstance(label, str) or not label:
            raise ValueError("[[entries]].label must be a non-empty string")
        if not isinstance(icon, str) or not icon:
            raise ValueError("[[entries]].icon must be a non-empty string")

        kind = get_provider_kind(config, provider_name)
        thresholds = get_thresholds(entry)
        total = sum(run_request(kind, request) for request in get_requests(entry))
        rows.append([label, icon, total, get_severity(total, thresholds)])

    return rows


def build_status_payload(config):
    return {"f": build_status_rows(config)}


def write_status_file(payload, output_path):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main(argv=None):
    args = parse_args(argv)
    config = load_config()
    payload = build_status_payload(config)

    if args.dry_run:
        print(json.dumps(payload, indent=2))
        return 0

    output_path = resolve_output_path(config, args.output)
    write_status_file(payload, output_path)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
