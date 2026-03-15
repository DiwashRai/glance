import json
from pathlib import Path


def get_dummy_count(status_path, key, start, step=5):
    current = int(start)
    path = Path(status_path)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for row in data.get("f", []):
                if isinstance(row, list) and len(row) > 2 and str(row[0]) == key:
                    current = int(row[2])
                    break
        except Exception:
            pass
    return max(current - int(step), 0)
