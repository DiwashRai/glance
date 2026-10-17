"""Gates: measured limits that keep glance's code in the shape we want.

Run it through `just gates` (check), `just ratchet` (lower the baseline after the code improves)
or `just card` (what a change did to the numbers). AGENTS.md explains each gate.
"""

from __future__ import annotations

import argparse
import copy
import io
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any, cast

from measures import (
    DEFAULT_LAYERS,
    METRICS,
    ROOT,
    Cyclomatic,
    FileReport,
    cyclomatic,
    fan_out,
    layer_totals,
    measure,
)

BASELINE = ROOT / "quality-baseline.json"
SHORT = {
    "optional_sig": "optional",
    "try_allowed": "try_ok",
    "broad_except": "broad",
    "suppressions": "suppress",
}
EXCEPTIONS = {
    "cognitive_exceptions": "cognitive",
    "cyclomatic_exceptions": "cyclomatic",
    "module_exceptions": "module_lines",
}

# ---- Gates ---------------------------------------------------------------------------------


@dataclass
class Result:
    name: str
    ok: bool
    summary: str
    details: list[str] = field(default_factory=list[str])
    warn: bool = False


def _over(scores: dict[str, int], exceptions: dict[str, int], limit: int) -> list[str]:
    return [
        f"{key}  {score} > {exceptions.get(key, limit)}"
        for key, score in sorted(scores.items())
        if score > exceptions.get(key, limit)
    ]


def check_cognitive(reports: list[FileReport], baseline: dict[str, Any]) -> Result:
    limit: int = baseline["limits"]["cognitive"]
    exceptions: dict[str, int] = baseline["cognitive_exceptions"]
    scores = {key: score for report in reports for key, score in report.functions.items()}
    worst = max(scores.values(), default=0)
    summary = f"no function over {limit}, {len(exceptions)} legacy exceptions, worst {worst}"
    over = _over(scores, exceptions, limit)
    return Result("cognitive", not over, summary, over)


def check_cyclomatic(run: Cyclomatic, baseline: dict[str, Any]) -> Result:
    if run.error:
        return Result("cyclomatic", False, "ruff failed to run", list(run.error))
    limit: int = baseline["limits"]["cyclomatic"]
    exceptions: dict[str, int] = baseline["cyclomatic_exceptions"]
    summary = f"no function over {limit} (ruff C901), {len(exceptions)} legacy exceptions"
    over = _over(run.scores, exceptions, limit)
    return Result("cyclomatic", not over, summary, over)


def check_fan_out(counts: dict[str, int], baseline: dict[str, Any]) -> Result:
    limit: int = baseline["limits"]["fan_out"]
    over = [f"{m}  imports {n} glance modules" for m, n in sorted(counts.items()) if n > limit]
    worst = max(counts.values(), default=0)
    summary = f"no module imports over {limit} glance modules, worst {worst}"
    return Result("fan-out", not over, summary, over)


def check_module_size(reports: list[FileReport], baseline: dict[str, Any]) -> Result:
    limit: int = baseline["limits"]["module_lines"]
    exceptions: dict[str, int] = baseline["module_exceptions"]
    over = _over({r.path: r.code_lines for r in reports}, exceptions, limit)
    summary = f"code lines per module <= {limit}, {len(exceptions)} legacy exceptions"
    return Result("module size", not over, summary, over)


def check_defensive(totals: dict[str, dict[str, list[str]]], baseline: dict[str, Any]) -> Result:
    allowed: dict[str, dict[str, int]] = baseline["allowed"]
    over: list[str] = []
    for layer, metrics in sorted(totals.items()):
        for metric, places in metrics.items():
            cap = allowed.get(layer, {}).get(metric, 0)
            if len(places) > cap:
                over.append(f"{layer}.{metric}: {len(places)} > {cap}")
                over += [f"    {place}" for place in places]
    return Result("defensive", not over, "counts per layer within the baseline", over)


def _flatten(baseline: dict[str, Any]) -> dict[str, int]:
    flat = {f"limits.{k}": v for k, v in baseline["limits"].items()}
    for layer, metrics in baseline["allowed"].items():
        flat |= {f"allowed.{layer}.{metric}": value for metric, value in metrics.items()}
    for key in EXCEPTIONS:
        flat |= {f"{key}.{name}": value for name, value in baseline[key].items()}
    return flat


def raised_keys(old: dict[str, Any], new: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Return (everything that went up, the subset with no new `raises` entry)."""
    old_flat = _flatten(old)
    raised = sorted(k for k, v in _flatten(new).items() if v > old_flat.get(k, 0))
    reasons = {entry["what"] for entry in new["raises"][len(old["raises"]) :]}
    return raised, [key for key in raised if key not in reasons]


def check_raises(baseline: dict[str, Any]) -> Result:
    committed = git_show("HEAD", BASELINE.name)
    if not committed:
        return Result("baseline", True, "no committed baseline yet")
    raised, missing = raised_keys(json.loads(committed), baseline)
    details = [f"{key} went up without a 'raises' entry" for key in missing]
    summary = (
        f"{len(raised)} raised, {len(missing)} without a reason" if raised else "nothing loosened"
    )
    return Result("baseline", not missing, summary, details)


def check_budget(reports: list[FileReport], baseline: dict[str, Any]) -> Result:
    budget: dict[str, int] = baseline["budget"]
    total = sum(r.code_lines for r in reports if r.layer != "tooling")
    added = total - budget["start_lines"]
    summary = f"stage {budget['stage']}: {added:+} of {budget['max_new_lines']} new lines"
    over = added > budget["max_new_lines"]
    details = ["over budget: do a simplification pass before the next stage"] if over else []
    return Result("size budget", True, summary, details, warn=over)


# ---- Baseline ------------------------------------------------------------------------------


def git_show(ref: str, path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return result.stdout if result.returncode == 0 else ""


def load_baseline() -> dict[str, Any]:
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def save_baseline(baseline: dict[str, Any]) -> None:
    BASELINE.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8", newline="\n")


def current_scores(reports: list[FileReport], run: Cyclomatic) -> dict[str, dict[str, int]]:
    return {
        "cognitive_exceptions": {k: v for r in reports for k, v in r.functions.items()},
        "cyclomatic_exceptions": run.scores,
        "module_exceptions": {r.path: r.code_lines for r in reports},
    }


def ratchet(baseline: dict[str, Any], reports: list[FileReport], run: Cyclomatic) -> list[str]:
    changes: list[str] = []
    for layer, metrics in layer_totals(reports).items():
        caps = baseline["allowed"].setdefault(layer, {})
        for metric, places in metrics.items():
            if len(places) < caps.get(metric, 0):
                changes.append(f"allowed.{layer}.{metric}: {caps[metric]} -> {len(places)}")
                caps[metric] = len(places)
    for key, current in current_scores(reports, run).items():
        changes += _lower(baseline, key, current)
    return changes


def _lower(baseline: dict[str, Any], key: str, current: dict[str, int]) -> list[str]:
    limit: int = baseline["limits"][EXCEPTIONS[key]]
    changes: list[str] = []
    exceptions: dict[str, int] = baseline[key]
    for name, cap in list(exceptions.items()):
        now = current.get(name, 0)
        if now <= limit:
            del exceptions[name]
            changes.append(f"{key}: {name} removed (now {now})")
        elif now < cap:
            exceptions[name] = now
            changes.append(f"{key}: {name} {cap} -> {now}")
    return changes


def init_baseline(reports: list[FileReport], run: Cyclomatic) -> dict[str, Any]:
    limits = {"cognitive": 15, "cyclomatic": 10, "module_lines": 1000, "fan_out": 5}
    totals = layer_totals(reports)
    scores = current_scores(reports, run)
    baseline: dict[str, Any] = {
        "version": 1,
        "layers": DEFAULT_LAYERS,
        "limits": limits,
        "allowed": {
            layer: {m: len(totals.get(layer, {}).get(m, [])) for m in METRICS}
            for layer in DEFAULT_LAYERS
        },
    }
    for key, limit_name in EXCEPTIONS.items():
        limit = limits[limit_name]
        baseline[key] = {k: v for k, v in sorted(scores[key].items()) if v > limit}
    baseline["budget"] = {
        "stage": 1,
        "start_lines": sum(r.code_lines for r in reports if r.layer != "tooling"),
        "max_new_lines": 1300,
    }
    baseline["raises"] = []
    return baseline


# ---- Output --------------------------------------------------------------------------------


class Style:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def paint(self, text: str, code: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

    def mark(self, result: Result) -> str:
        if not result.ok:
            return self.paint("✗", "31")
        return self.paint("!", "33") if result.warn else self.paint("✓", "32")


def make_style() -> Style:
    # Windows pipes can use a non-UTF-8 code page; force UTF-8 for the marks.
    cast("io.TextIOWrapper[Any]", sys.stdout).reconfigure(encoding="utf-8")
    return Style(sys.stdout.isatty() or bool(os.environ.get("FORCE_COLOR")))


def print_table(
    totals: dict[str, dict[str, list[str]]], baseline: dict[str, Any], style: Style
) -> None:
    allowed: dict[str, dict[str, int]] = baseline["allowed"]
    header = "".join(f"{SHORT.get(m, m):>11}" for m in METRICS)
    print(style.paint(f"    {'layer':<10}{header}", "2"))
    for layer in sorted(totals):
        cells: list[str] = []
        for metric in METRICS:
            count, cap = len(totals[layer][metric]), allowed.get(layer, {}).get(metric, 0)
            colour = "31" if count > cap else ("32" if count < cap else "0")
            cells.append(style.paint(f"{count}/{cap}".rjust(11), colour))
        print(f"    {layer:<10}{''.join(cells)}")


@dataclass
class Run:
    results: list[Result]
    totals: dict[str, dict[str, list[str]]]
    baseline: dict[str, Any]
    files: int
    can_ratchet: bool


def print_report(run: Run) -> bool:
    style = make_style()
    print(style.paint(f"gates · {run.files} files", "1"))
    for result in run.results:
        print(f"  {style.mark(result)} {result.name:<12} {result.summary}")
        for line in result.details:
            print(style.paint(f"      {line}", "31" if not result.ok else "33"))
        if result.name == "defensive":
            print_table(run.totals, run.baseline, style)
    if run.can_ratchet:
        print(style.paint("  ratchet available: run `just ratchet` to lock in the gain", "36"))
    passed = all(r.ok for r in run.results)
    print(style.paint("PASS", "1;32") if passed else style.paint("FAIL", "1;31"))
    return passed


def check_all(baseline: dict[str, Any]) -> Run:
    reports = measure(baseline["layers"])
    totals = layer_totals(reports)
    ruff_run = cyclomatic()
    results = [
        check_cognitive(reports, baseline),
        check_cyclomatic(ruff_run, baseline),
        check_fan_out(fan_out(), baseline),
        check_module_size(reports, baseline),
        check_defensive(totals, baseline),
        check_raises(baseline),
        check_budget(reports, baseline),
    ]
    can_ratchet = bool(ratchet(copy.deepcopy(baseline), reports, ruff_run))
    return Run(results, totals, baseline, len(reports), can_ratchet)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ratchet", action="store_true", help="lower the baseline, never raise it")
    parser.add_argument("--init", action="store_true", help="write the first baseline")
    args = parser.parse_args(argv)
    if args.init:
        save_baseline(init_baseline(measure(DEFAULT_LAYERS), cyclomatic()))
        print(f"wrote {BASELINE.name}")
        return 0
    baseline = load_baseline()
    if args.ratchet:
        changes = ratchet(baseline, measure(baseline["layers"]), cyclomatic())
        save_baseline(baseline)
        print("\n".join(changes) if changes else "nothing to ratchet")
        return 0
    return 0 if print_report(check_all(baseline)) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
