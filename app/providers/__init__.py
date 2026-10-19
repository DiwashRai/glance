"""Where counts come from. Each provider is a `count` function, taking its `[providers.<name>]`
table and the entry's requests, which it checks itself."""

from collections.abc import Callable, Mapping, Sequence

from . import dummy, github_gh, jira, outlook_emails, todoist

COUNTS: dict[str, Callable[[Mapping[str, object], Sequence[Mapping[str, object]]], int]] = {
    "dummy": dummy.count,
    "github-gh": github_gh.count,
    "jira": jira.count,
    "outlook": outlook_emails.count,
    "todoist": todoist.count,
}
