import json


def format_status_payload(payload):
    lines = ["{"]
    items = list(payload.items())

    for index, (key, value) in enumerate(items):
        suffix = "," if index < len(items) - 1 else ""
        dumped_key = json.dumps(key, ensure_ascii=False)

        if key == "f" and isinstance(value, list):
            lines.append(f"  {dumped_key}: [")
            for row_index, row in enumerate(value):
                row_suffix = "," if row_index < len(value) - 1 else ""
                lines.append(f"    {json.dumps(row, ensure_ascii=False)}{row_suffix}")
            lines.append(f"  ]{suffix}")
            continue

        dumped_value = json.dumps(value, indent=2, ensure_ascii=False)
        value_lines = dumped_value.splitlines()
        lines.append(f"  {dumped_key}: {value_lines[0]}")
        for line in value_lines[1:]:
            lines.append(f"  {line}")
        lines[-1] = f"{lines[-1]}{suffix}"

    lines.append("}")
    return "\n".join(lines) + "\n"
