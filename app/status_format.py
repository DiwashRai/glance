import json
from typing import cast

from app.types import CountsRow, StatusFile, TimeBlockRow


def _append_inline_rows(
    lines: list[str], key: str, rows: list[CountsRow] | list[TimeBlockRow], suffix: str
) -> None:
    dumped_key = json.dumps(key, ensure_ascii=False)
    lines.append(f"  {dumped_key}: [")
    for row_index, row in enumerate(rows):
        row_suffix = "," if row_index < len(rows) - 1 else ""
        lines.append(f"    {json.dumps(row, ensure_ascii=False)}{row_suffix}")
    lines.append(f"  ]{suffix}")


def format_status_payload(payload: StatusFile) -> str:
    lines = ["{"]
    items = list(payload.items())

    for index, (key, value) in enumerate(items):
        suffix = "," if index < len(items) - 1 else ""
        if key == "f" and isinstance(value, list):
            _append_inline_rows(lines, key, cast(list[CountsRow], value), suffix)
            continue

        if key == "tb" and isinstance(value, list):
            _append_inline_rows(lines, key, cast(list[TimeBlockRow], value), suffix)
            continue

        dumped_key = json.dumps(key, ensure_ascii=False)
        dumped_value = json.dumps(value, indent=2, ensure_ascii=False)
        value_lines = dumped_value.splitlines()
        lines.append(f"  {dumped_key}: {value_lines[0]}")
        for line in value_lines[1:]:
            lines.append(f"  {line}")
        lines[-1] = f"{lines[-1]}{suffix}"

    lines.append("}")
    return "\n".join(lines) + "\n"
