import json
from pathlib import Path
from typing import ClassVar, cast

from app.providers.registry import provider_registry
from app.types import ProviderContext, StatusFile


def get_dummy_count(status_path: Path, key: str, start: int, step: int = 5) -> int:
    current = int(start)
    if status_path.exists() and status_path.is_file():
        with status_path.open(encoding="utf-8") as file:
            data = cast(StatusFile, json.load(file))

        for label, _, count, _ in data["f"]:
            if label == key:
                current = count
                break

    return max(current - int(step), 0)


def _parse_dummy_input(ctx: ProviderContext) -> tuple[Path, list[tuple[str, int, int]]]:
    output_path = ctx.provider_config.get("output_path")
    if not isinstance(output_path, str) or not output_path:
        raise ValueError("Dummy provider requires 'output_path' to be a non-empty string")

    parsed_requests: list[tuple[str, int, int]] = []
    for request in ctx.requests:
        key = request.get("key")
        if not isinstance(key, str) or not key:
            raise ValueError("Dummy requests require a non-empty 'key' string")

        start = request.get("start")
        step = request.get("step", 5)
        if not isinstance(start, int) or not isinstance(step, int):
            raise ValueError("Dummy requests require 'start' and 'step' to be ints")

        parsed_requests.append((key, start, step))

    return Path(output_path), parsed_requests


class DummyProvider:
    kind: ClassVar[str] = "dummy"

    def count(self, ctx: ProviderContext) -> int:
        output_path, parsed_requests = _parse_dummy_input(ctx)
        total = 0
        for key, start, step in parsed_requests:
            total += get_dummy_count(output_path, key, start, step)

        return total


provider_registry.register(DummyProvider)
