"""Measuring glance's code: defensive patterns, complexity, size and imports.

Used by fitness.py (the gates) and card.py (what a change did to the numbers).
"""

from __future__ import annotations

import ast
import fnmatch
import io
import json
import re
import subprocess
import sys
import tokenize
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import complexipy
import grimp

ROOT = Path(__file__).resolve().parent.parent
MEASURED = ("app", "scripts", "glance.py", "glance_v2.py", "update_status.py")
ENTRY_POINTS = ("glance", "glance_v2", "update_status")
METRICS = (
    "is_none",
    "optional_sig",
    "isinstance",
    "try",
    "try_allowed",
    "broad_except",
    "suppressions",
)
SUPPRESSION_MARKERS = ("noqa", "pyright: ignore", "type: ignore")
# First match wins. Patterns use fnmatch, where "*" also matches "/".
DEFAULT_LAYERS = {
    "core": ["app/core/*"],
    "handlers": ["glance.py", "glance_v2.py", "update_status.py"],
    "ui": ["app/ui/*"],
    "tooling": ["scripts/*"],
    "boundary": ["app/*"],
}
BROAD = {"Exception", "BaseException"}
BUILTIN_TYPES = {
    "bool",
    "bytearray",
    "bytes",
    "complex",
    "dict",
    "float",
    "frozenset",
    "int",
    "list",
    "set",
    "str",
    "tuple",
}


@dataclass(frozen=True)
class FileReport:
    path: str
    layer: str
    code_lines: int
    hits: dict[str, list[int]]
    functions: dict[str, int]


# ---- Defensive patterns --------------------------------------------------------------------


def _is_none(node: ast.expr) -> bool:
    match node:
        case ast.Constant(value=None):
            return True
        case _:
            return False


def _is_optional(node: ast.expr) -> bool:
    for sub in ast.walk(node):
        match sub:
            case ast.BinOp(op=ast.BitOr(), left=left, right=right):
                if _is_none(left) or _is_none(right):
                    return True
            case ast.Subscript(value=ast.Name(id="Optional")):
                return True
            case _:
                continue
    return False


def _is_broad(handler: ast.ExceptHandler) -> bool:
    match handler.type:
        case None:
            return True
        case ast.Name(id=name):
            return name in BROAD
        case ast.Tuple(elts=elts):
            return any(_is_broad(ast.ExceptHandler(type=elt, body=[])) for elt in elts)
        case _:
            return False


class _Walker(ast.NodeVisitor):
    def __init__(self, comments: dict[int, str]) -> None:
        self.comments = comments
        self.hits: dict[str, list[int]] = {metric: [] for metric in METRICS}

    def add(self, metric: str, node: ast.AST) -> None:
        self.hits[metric].append(getattr(node, "lineno", 0))

    def visit_Compare(self, node: ast.Compare) -> None:
        uses_is = any(type(op) in (ast.Is, ast.IsNot) for op in node.ops)
        if uses_is and any(_is_none(x) for x in [node.left, *node.comparators]):
            self.add("is_none", node)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        match node.func:
            case ast.Name(id="isinstance"):
                self.add("isinstance", node)
            case _:
                pass
        self.generic_visit(node)

    def visit_MatchClass(self, node: ast.MatchClass) -> None:
        """`case str(x)` is an isinstance check in other clothes, so it counts as one."""
        match node.cls:
            case ast.Name(id=name) if name in BUILTIN_TYPES:
                self.add("isinstance", node)
            case _:
                pass
        self.generic_visit(node)

    def _visit_try(self, node: ast.Try | ast.TryStar) -> None:
        allowed = "boundary:" in self.comments.get(node.lineno, "")
        self.add("try_allowed" if allowed else "try", node)
        self.generic_visit(node)

    visit_Try = _visit_try
    visit_TryStar = _visit_try

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if _is_broad(node):
            self.add("broad_except", node)
        self.generic_visit(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        args = node.args
        params = [*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg]
        annotations = [p.annotation for p in params if p and p.annotation]
        annotations += [node.returns] if node.returns else []
        for annotation in annotations:
            if _is_optional(annotation):
                self.add("optional_sig", annotation)
        self.generic_visit(node)

    visit_FunctionDef = _visit_function
    visit_AsyncFunctionDef = _visit_function


def _comments(source: str) -> dict[int, str]:
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    return {tok.start[0]: tok.string for tok in tokens if tok.type == tokenize.COMMENT}


def layer_of(path: str, layers: dict[str, list[str]]) -> str:
    for layer, patterns in layers.items():
        if any(fnmatch.fnmatch(path, pattern) for pattern in patterns):
            return layer
    return "other"


def analyse(path: str, source: str, layers: dict[str, list[str]]) -> FileReport:
    comments = _comments(source)
    walker = _Walker(comments)
    walker.visit(ast.parse(source, filename=path))
    marked = [
        line for line, text in comments.items() if any(m in text for m in SUPPRESSION_MARKERS)
    ]
    walker.hits["suppressions"] = sorted(marked)
    stripped = (line.strip() for line in source.splitlines())
    code_lines = sum(1 for line in stripped if line and not line.startswith("#"))
    functions = {
        f"{path}::{fn.name}": fn.complexity for fn in complexipy.code_complexity(source).functions
    }
    return FileReport(path, layer_of(path, layers), code_lines, walker.hits, functions)


def measured_files() -> list[str]:
    paths: list[Path] = []
    for entry in MEASURED:
        target = ROOT / entry
        paths += sorted(target.rglob("*.py")) if target.is_dir() else [target]
    return [p.relative_to(ROOT).as_posix() for p in paths if "__pycache__" not in p.parts]


def measure(layers: dict[str, list[str]]) -> list[FileReport]:
    files = measured_files()
    return [analyse(path, (ROOT / path).read_text(encoding="utf-8"), layers) for path in files]


def layer_totals(reports: list[FileReport]) -> dict[str, dict[str, list[str]]]:
    totals: dict[str, dict[str, list[str]]] = {}
    for report in reports:
        layer = totals.setdefault(report.layer, {metric: [] for metric in METRICS})
        for metric, lines in report.hits.items():
            layer[metric] += [f"{report.path}:{line}" for line in lines]
    return totals


# ---- Cyclomatic complexity (ruff C901) -----------------------------------------------------

TOO_COMPLEX = re.compile(r"`(?P<name>[^`]+)` is too complex \((?P<score>\d+) >")


@dataclass(frozen=True)
class Cyclomatic:
    scores: dict[str, int]
    error: tuple[str, ...] = ()


def parse_ruff(code: int, stdout: str, stderr: str) -> Cyclomatic:
    """Ruff exits 0 when clean and 1 with findings. Anything else, or 1 with none, is a failure."""
    findings = cast("list[dict[str, Any]]", json.loads(stdout)) if code in (0, 1) else []
    scores: dict[str, int] = {}
    for item in findings:
        found = TOO_COMPLEX.search(str(item["message"]))
        if found:
            path = Path(str(item["filename"])).resolve().relative_to(ROOT).as_posix()
            scores[f"{path}::{found['name']}"] = int(found["score"])
    if code == 0 or (code == 1 and scores):
        return Cyclomatic(scores)
    error = (stderr or stdout).strip().splitlines() or [f"ruff exited with {code}"]
    return Cyclomatic({}, tuple(error))


def cyclomatic() -> Cyclomatic:
    command = [sys.executable, "-m", "ruff", "check", "--select", "C901", "--output-format"]
    command += ["json", "--quiet", "--no-cache", *MEASURED]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    return parse_ruff(result.returncode, result.stdout, result.stderr)


# ---- Fan-out (grimp) -----------------------------------------------------------------------


def _from_import(module: str, names: list[ast.alias], modules: set[str]) -> set[str]:
    """`from a import b` imports the submodule a.b if there is one, otherwise names from a."""
    submodules = {f"{module}.{alias.name}" for alias in names} & modules
    return submodules or {module}


def entry_point_imports(source: str, modules: set[str]) -> set[str]:
    """The glance modules an entry point imports. grimp only reads packages, so this uses ast."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        match node:
            case ast.Import(names=names):
                found |= {alias.name for alias in names}
            case ast.ImportFrom(module=module, names=names) if module:
                found |= _from_import(module, names, modules)
            case _:
                pass
    return found & modules


def fan_out() -> dict[str, int]:
    graph = grimp.build_graph("app", include_external_packages=False)
    modules = set(graph.modules)
    counts = {m: len(graph.find_modules_directly_imported_by(m) & modules) for m in modules}
    for name in ENTRY_POINTS:
        source = (ROOT / f"{name}.py").read_text(encoding="utf-8")
        counts[name] = len(entry_point_imports(source, modules))
    return counts
