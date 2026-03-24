import json
from collections.abc import Sequence
from typing import ClassVar

from app.providers.registry import provider_registry
from app.types import ProviderContext
from app.utils import run_no_window


def get_gh_pr_count(requests: Sequence[Sequence[str]]) -> int:
    if not isinstance(requests, list) or not requests:
        raise TypeError("requests must be provided as a non-empty list")

    urls: dict[str, object] = {}
    for args in requests:
        if not isinstance(args, list) or not args:
            raise TypeError("each request must be a non-empty list")

        command = ["gh", "search", "prs", "--json", "url", *args]
        completed = run_no_window(command)
        if completed.returncode != 0:
            message = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(
                f"gh search prs failed with exit code {completed.returncode}: {message}"
            )
        results = json.loads(completed.stdout)
        for result in results:
            urls[result["url"]] = True

    return len(urls)


def _parse_github_gh_input(ctx: ProviderContext) -> list[list[str]]:
    args_list: list[list[str]] = []
    for request in ctx.requests:
        args = request.get("args")
        if not isinstance(args, list) or not args:
            raise ValueError("GitHub requests require a non-empty 'args' list")

        parsed_args: list[str] = []
        for arg in args:
            if not isinstance(arg, str) or not arg:
                raise ValueError("GitHub args items must be non-empty strings")
            parsed_args.append(arg)

        args_list.append(parsed_args)

    return args_list


class GithubGhProvider:
    kind: ClassVar[str] = "github-gh"

    def count(self, ctx: ProviderContext) -> int:
        return get_gh_pr_count(_parse_github_gh_input(ctx))


provider_registry.register(GithubGhProvider)
