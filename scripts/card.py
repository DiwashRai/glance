"""Change card: what a change did to glance's gate numbers.

`just card [BASE]` compares the working tree (committed or not) with BASE, by default `main`.
"""

from __future__ import annotations

import subprocess
import sys

from fitness import git_show, load_baseline
from measures import MEASURED, METRICS, ROOT, FileReport, analyse

NOTABLE = 10  # functions at or above this, before or after, are listed by name


def git_lines(*args: str) -> list[str]:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)
    return [line for line in result.stdout.splitlines() if line]


def changed_files(base: str) -> list[str]:
    names = git_lines("diff", "--name-only", base, "--", "*.py")
    names += git_lines("ls-files", "--others", "--exclude-standard", "--", "*.py")
    return sorted({n for n in names if n.startswith(MEASURED)})


def report_for(path: str, source: str, layers: dict[str, list[str]]) -> FileReport:
    if source:
        return analyse(path, source, layers)
    return FileReport(path, "", 0, {m: [] for m in METRICS}, {})


def read_now(path: str) -> str:
    target = ROOT / path
    return target.read_text(encoding="utf-8") if target.exists() else ""


def change_text(was: int, now: int, limit: int) -> str:
    """Describe a score change. -1 means the function doesn't exist on that side."""
    if now < 0:
        return "removed"
    text = f"new {now}" if was < 0 else f"{was} -> {now}"
    return text + ("  over limit" if now > limit else "")


def function_rows(before: list[FileReport], after: list[FileReport], limit: int) -> list[str]:
    old = {k: v for r in before for k, v in r.functions.items()}
    new = {k: v for r in after for k, v in r.functions.items()}
    pairs = [(k, old.get(k, -1), new.get(k, -1)) for k in sorted(old.keys() | new.keys())]
    changed = [pair for pair in pairs if pair[1] != pair[2]]
    notable = [pair for pair in changed if max(pair[1], pair[2]) >= NOTABLE]
    notable.sort(key=lambda pair: pair[2], reverse=True)
    rows = [f"  {key:<60} {change_text(was, now, limit)}" for key, was, now in notable]
    quiet = len(changed) - len(rows)
    return [*rows, f"  ...and {quiet} more below {NOTABLE}"] if quiet else rows


def layers_in(before: list[FileReport], after: list[FileReport]) -> list[str]:
    return sorted({r.layer for r in before + after if r.layer})


def hit_count(reports: list[FileReport], layer: str, metric: str) -> int:
    return sum(len(r.hits[metric]) for r in reports if r.layer == layer)


def metric_rows(before: list[FileReport], after: list[FileReport]) -> list[str]:
    rows: list[str] = []
    for layer in layers_in(before, after):
        for metric in METRICS:
            was, now = hit_count(before, layer, metric), hit_count(after, layer, metric)
            if was != now:
                rows.append(f"  {layer:<10} {metric:<14} {was:>5} -> {now:<5} ({now - was:+})")
    return rows


def line_rows(before: list[FileReport], after: list[FileReport]) -> list[str]:
    rows: list[str] = []
    for layer in layers_in(before, after):
        was = sum(r.code_lines for r in before if r.layer == layer)
        now = sum(r.code_lines for r in after if r.layer == layer)
        rows.append(f"  {layer:<10} {now - was:+} code lines")
    return rows


def main(argv: list[str]) -> int:
    base = argv[0] if argv else "main"
    baseline = load_baseline()
    layers: dict[str, list[str]] = baseline["layers"]
    files = changed_files(base)
    before = [report_for(p, git_show(base, p), layers) for p in files]
    after = [report_for(p, read_now(p), layers) for p in files]
    sections = [
        (
            "functions whose cognitive complexity changed",
            function_rows(before, after, baseline["limits"]["cognitive"]),
        ),
        ("defensive code in changed files", metric_rows(before, after)),
        ("size by layer", line_rows(before, after)),
    ]
    print(f"change card · working tree vs {base} · {len(files)} Python files changed")
    for title, rows in sections:
        print(f"\n{title}")
        print("\n".join(rows) if rows else "  (no change)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
