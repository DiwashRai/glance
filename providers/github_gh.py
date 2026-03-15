import argparse
import json
import subprocess
import sys


def _run_no_window(*args, **kwargs):
    if sys.platform.startswith("win"):
        creationflags = kwargs.pop("creationflags", 0)
        kwargs["creationflags"] = creationflags | getattr(
            subprocess, "CREATE_NO_WINDOW", 0
        )

        startupinfo = kwargs.get("startupinfo")
        if startupinfo is None:
            startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
        kwargs["startupinfo"] = startupinfo

        if "stdin" not in kwargs and "input" not in kwargs:
            kwargs["stdin"] = subprocess.DEVNULL

    return subprocess.run(*args, **kwargs)


def get_gh_pr_count(requests):
    if not isinstance(requests, list) or not requests:
        raise TypeError("requests must be provided as a non-empty list")

    urls = {}
    for args in requests:
        if not isinstance(args, list) or not args:
            raise TypeError("each request must be a non-empty list")

        command = ["gh", "search", "prs", "--json", "url", *args]
        completed = _run_no_window(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            message = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(
                f"gh search prs failed with exit code {completed.returncode}: {message}"
            )
        results = json.loads(completed.stdout)
        for result in results:
            urls[result["url"]] = True

    return len(urls)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Return GitHub PR search results from gh CLI."
    )
    parser.add_argument(
        "args",
        nargs="+",
        help="Arguments to pass through to gh search prs.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    print(get_gh_pr_count([args.args]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
