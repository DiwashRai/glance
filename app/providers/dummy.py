import json
from pathlib import Path
from typing import cast

from app.types import StatusFile


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
