"""The collector and its providers, with each outside source (Todoist, Jira, gh, the Outlook
script) replaced by a fake that answers the way it does."""

import json
import subprocess
from pathlib import Path
from typing import Any

import msgspec
import pytest

import update_status
from app.providers import github_gh, jira, outlook_emails, todoist
from app.types import CountsRow


def ran(answer: object, code: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], code, json.dumps(answer), "")


def collector(text: str) -> update_status.Collector:
    return msgspec.convert(update_status.tomllib.loads(text), update_status.Collector)


def entry(provider: str, label: str) -> str:
    return (
        f'[[entries]]\nprovider = "{provider}"\nlabel = "{label}"\nicon = ""\n'
        "thresholds = { low = 1, medium = 2, high = 3 }\n"
        'requests = [{ key = "k", start = 4, step = 1 }]\n'
    )


def test_the_demo_config_counts_down_and_is_written_a_row_to_a_line() -> None:
    config = update_status.load_config(Path(__file__).parents[1] / "config.toml")
    rows = update_status.build_status_rows(config)
    assert [(label, count) for label, _, count, _ in rows] == [
        ("email/inbox", 13),
        ("tasks/today", 7),
        ("github/reviews", 2),
    ]
    rows = [("email/inbox", "mail", 13, 2), ("tasks/today", "todo", 7, 2)]
    assert update_status.counts_json(rows) == (
        '{\n  "f": [\n    ["email/inbox", "mail", 13, 2],\n    ["tasks/today", "todo", 7, 2]\n'
        "  ]\n}\n"
    )
    assert update_status.counts_json([]) == '{\n  "f": [\n  ]\n}\n'


def test_an_entry_that_fails_is_minus_one_and_the_others_still_count() -> None:
    providers = '[providers.demo]\nkind = "dummy"\noutput_path = "nowhere.json"\n'
    providers += '[providers.odd]\nkind = "fax"\n'  # no such provider
    text = providers + entry("demo", "ok") + entry("missing", "a") + entry("odd", "b")
    rows: list[CountsRow] = update_status.build_status_rows(collector(text))
    assert rows == [("ok", "", 3, 3), ("a", "", -1, 3), ("b", "", -1, 3)]


def test_a_bad_config_is_refused_naming_the_key() -> None:
    with pytest.raises(msgspec.ValidationError, match=r"entries\[0\]\.label"):
        collector(entry("demo", ""))


def test_todoist_pages_and_counts_a_task_once(monkeypatch: pytest.MonkeyPatch) -> None:
    pages = {
        ("today", ""): {"results": [{"id": "1"}, {"id": "2"}], "next_cursor": "c2"},
        ("today", "c2"): {"results": [{"id": "3"}], "next_cursor": None},
        ("overdue", ""): {"results": [{"id": "2"}, {"id": "4"}], "next_cursor": None},
    }

    def page(token: str, query: str, lang: str, cursor: str) -> tuple[str, str]:
        assert token == "t"
        return query, cursor

    def load(asked: tuple[str, str]) -> bytes:
        return json.dumps(pages[asked]).encode()

    monkeypatch.setattr(todoist, "_page_request", page)
    monkeypatch.setattr(todoist, "_load_page", load)
    requests = [{"filter": "today"}, {"query": "overdue"}]
    assert todoist.count({"kind": "todoist", "api_token": "t"}, requests) == 4


def test_jira_pages_until_the_total(monkeypatch: pytest.MonkeyPatch) -> None:
    class Answer:
        def __init__(self, body: dict[str, Any]) -> None:
            self.body = json.dumps(body).encode()

        def __enter__(self) -> "Answer":
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def read(self) -> bytes:
            return self.body

    def urlopen(request: Any) -> Answer:
        start = json.loads(request.data)["startAt"]
        issues = [{"id": str(n)} for n in range(start, min(start + 2, 3))]
        return Answer({"issues": issues, "total": 3})

    monkeypatch.setattr(jira.urllib.request, "urlopen", urlopen)
    provider = {"kind": "jira", "base_url": "https://x", "api_version": 2, "api_token": "t"}
    assert jira.count(provider, [{"jql": ["a", "b"]}]) == 3


def test_gh_counts_a_pr_found_twice_once(monkeypatch: pytest.MonkeyPatch) -> None:
    found = {"--author=@me": [{"url": "u1"}, {"url": "u2"}], "--assignee=@me": [{"url": "u2"}]}

    def gh(command: list[str]) -> subprocess.CompletedProcess[str]:
        return ran(found[command[-1]])

    monkeypatch.setattr(github_gh, "run_no_window", gh)
    requests = [{"args": ["--author=@me"]}, {"args": ["--assignee=@me"]}]
    assert github_gh.count({"kind": "github-gh"}, requests) == 2


def test_outlook_adds_named_and_numbered_folders_running_the_script_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def script(command: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return ran({"default": {"6": 2}, "me@x.com": {"inbox": 3, "team": 4}})

    monkeypatch.setattr(outlook_emails, "run_no_window", script)
    provider = {"kind": "outlook", "outlook_store": "Me@x.com"}
    assert outlook_emails.count(provider, [{"folders": ["6", "Team"]}]) == 6
    assert outlook_emails.count(provider, [{"folders": ["6", "inbox"]}]) == 5
    assert len(calls) == 1 and calls[0][-2:] == ["-DefaultFolderIds", "6"]

    def failing(command: list[str]) -> subprocess.CompletedProcess[str]:
        return ran({"error": "no Outlook"})

    # another store, as the script's answers are kept for the rest of the run
    monkeypatch.setattr(outlook_emails, "run_no_window", failing)
    with pytest.raises(RuntimeError, match="no Outlook"):
        outlook_emails.count({"outlook_store": "other@x.com"}, [{"folders": ["inbox"]}])
