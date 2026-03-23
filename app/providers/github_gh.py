import argparse
import json
from collections.abc import Sequence

from app.utils import run_no_window


def get_gh_pr_count(requests: Sequence[str]) -> int:
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


def parse_args(argv: Sequence[str] | None = None):
    parser = argparse.ArgumentParser(description="Return GitHub PR search results from gh CLI.")
    parser.add_argument(
        "args",
        nargs="+",
        help="Arguments to pass through to gh search prs.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None):
    args = parse_args(argv)
    print(get_gh_pr_count([args.args]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
