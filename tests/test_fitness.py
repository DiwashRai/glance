import copy
from typing import Any

import fitness
import measures

LAYERS = {"core": ["app/core/*"], "boundary": ["app/*"]}

SAMPLE = """
from typing import Optional


def f(a: int | None, b: Optional[str]) -> None:
    if a is None or b is not None:
        return
    if isinstance(a, int):
        pass
    try:
        pass
    except Exception:
        pass
    try:  # boundary: reading a file the user controls
        pass
    except (ValueError, BaseException):
        pass
    x = 1  # noqa: E501
"""


def counts(path: str = "app/core/sample.py") -> dict[str, int]:
    report = measures.analyse(path, SAMPLE, LAYERS)
    return {metric: len(lines) for metric, lines in report.hits.items()}


def test_counts_each_defensive_pattern() -> None:
    assert counts() == {
        "is_none": 2,
        "optional_sig": 2,
        "isinstance": 1,
        "try": 1,
        "try_allowed": 1,
        "broad_except": 2,
        "suppressions": 1,
    }


def test_builtin_class_patterns_count_as_isinstance() -> None:
    source = (
        "def f(x: object, y: object) -> None:\n"
        "    match x:\n"
        "        case str(name):\n"
        "            pass\n"
        "        case {'n': int()}:\n"
        "            pass\n"
        "        case Point():\n"
        "            pass\n"
    )
    report = measures.analyse("app/x.py", source, LAYERS)
    assert report.hits["isinstance"] == [3, 5]


def test_return_none_is_not_optional() -> None:
    report = measures.analyse("app/x.py", "def g() -> None:\n    return\n", LAYERS)
    assert report.hits["optional_sig"] == []


def test_layers_first_match_wins() -> None:
    assert measures.layer_of("app/core/lists.py", LAYERS) == "core"
    assert measures.layer_of("app/providers/jira.py", LAYERS) == "boundary"
    assert measures.layer_of("glance.py", LAYERS) == "other"


def test_entry_point_imports_count_a_submodule_once() -> None:
    modules = {"app.types", "app.providers", "app.providers.registry"}
    source = "import os\nfrom app.types import X\nfrom app.providers import registry\n"
    found = measures.entry_point_imports(source, modules)
    assert found == {"app.types", "app.providers.registry"}


def baseline() -> dict[str, Any]:
    return {
        "layers": LAYERS,
        "limits": {"cognitive": 15, "cyclomatic": 10, "module_lines": 400, "fan_out": 5},
        "allowed": {"core": dict.fromkeys(measures.METRICS, 5)},
        "cognitive_exceptions": {"app/core/sample.py::f": 30},
        "cyclomatic_exceptions": {"app/core/sample.py::f": 12},
        "module_exceptions": {},
        "raises": [],
    }


def test_ratchet_lowers_and_never_raises() -> None:
    current = baseline()
    report = measures.analyse("app/core/sample.py", SAMPLE, LAYERS)
    run = measures.Cyclomatic({"app/core/sample.py::f": 11})
    changes = fitness.ratchet(current, [report], run)
    assert current["allowed"]["core"]["is_none"] == 2
    assert "app/core/sample.py::f" not in current["cognitive_exceptions"]
    assert current["cyclomatic_exceptions"]["app/core/sample.py::f"] == 11
    assert changes
    assert fitness.ratchet(current, [report], run) == []


def test_raising_a_limit_needs_a_reason() -> None:
    old = baseline()
    new = copy.deepcopy(old)
    new["allowed"]["core"]["try"] = 6
    raised, missing = fitness.raised_keys(old, new)
    assert raised == missing == ["allowed.core.try"]
    new["raises"].append({"what": "allowed.core.try", "reason": "test", "date": "2026-10-17"})
    assert fitness.raised_keys(old, new) == (["allowed.core.try"], [])
