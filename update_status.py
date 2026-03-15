import argparse
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib # type: ignore[import-not-found]
from pathlib import Path

from providers.dummy import get_dummy_count
from providers.github_gh import get_gh_pr_count
from providers.jira import get_issue_count
from providers.outlook_emails import get_unread_email_count
from providers.todoist import DEFAULT_FILTER, get_task_count
from status_format import format_status_payload


DEFAULT_CONFIG_PATH = "config.local.toml"
PROVIDER_FUNCTIONS = {
    "dummy": get_dummy_count,
    "github-gh": get_gh_pr_count,
    "jira": get_issue_count,
    "outlook": get_unread_email_count,
    "todoist": get_task_count,
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


def run_outlook_request(fetcher, request):
    folders = request.get("folders")
    if not isinstance(folders, list) or not folders:
        raise ValueError(
            "Outlook requests require a non-empty 'folders' list"
        )

    folder_list = []
    for folder in folders:
        if not isinstance(folder, str) or not folder:
            raise ValueError(
                "Outlook folder list items must be non-empty strings"
            )
        if folder.isdigit():
            folder_list.append(int(folder))
        else:
            folder_list.append(folder)

    if not folder_list:
        raise ValueError(
            "Outlook requests require at least one folder in 'folders'"
        )

    return fetcher(folder_list)


def run_jira_request(fetcher, provider_name, config, request):
    providers = get_table(config, "providers")
    provider = providers.get(provider_name)
    if not isinstance(provider, dict):
        raise ValueError(f"[providers.{provider_name}] must be a TOML table")

    base_url = provider.get("base_url")
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

    jqls = []
    for item in jql:
        if not isinstance(item, str) or not item:
            raise ValueError("Jira jql items must be non-empty strings")
        jqls.append(item)

    return fetcher(base_url, api_version, api_token, jqls)


def run_github_gh_request(fetcher, request):
    args = request.get("args")
    if not isinstance(args, list) or not args:
        raise ValueError("GitHub requests require a non-empty 'args' list")
    return fetcher([args])


def run_todoist_request(fetcher, provider_name, config, request):
    providers = get_table(config, "providers")
    provider = providers.get(provider_name)
    if not isinstance(provider, dict):
        raise ValueError(f"[providers.{provider_name}] must be a TOML table")

    api_token = provider.get("api_token")
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


def run_dummy_request(fetcher, config, request):
    key = request.get("key")
    if not isinstance(key, str) or not key:
        raise ValueError("Dummy requests require a non-empty 'key' string")
    return fetcher(
        resolve_output_path(config, None),
        key,
        int(request.get("start", 0)),
        int(request.get("step", 5)),
    )


def run_request(kind, provider_name, config, request):
    fetcher = PROVIDER_FUNCTIONS.get(kind)
    if fetcher is None:
        raise ValueError(f"Unsupported provider kind: {kind}")

    if kind == "outlook":
        return run_outlook_request(fetcher, request)

    if kind == "jira":
        return run_jira_request(fetcher, provider_name, config, request)

    if kind == "github-gh":
        return run_github_gh_request(fetcher, request)

    if kind == "todoist":
        return run_todoist_request(fetcher, provider_name, config, request)

    if kind == "dummy":
        return run_dummy_request(fetcher, config, request)

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
        total = sum(
            run_request(kind, provider_name, config, request)
            for request in get_requests(entry)
        )
        rows.append([label, icon, total, get_severity(total, thresholds)])

    return rows


def build_status_payload(config):
    return {"f": build_status_rows(config)}


def write_status_file(payload, output_path):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_status_payload(payload), encoding="utf-8")


def main(argv=None):
    args = parse_args(argv)
    config = load_config()
    payload = build_status_payload(config)

    if args.dry_run:
        print(format_status_payload(payload), end="")
        return 0

    output_path = resolve_output_path(config, args.output)
    write_status_file(payload, output_path)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
