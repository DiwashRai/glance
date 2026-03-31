import json
from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar, cast

from app.providers.registry import provider_registry
from app.types import ProviderContext
from app.utils import run_no_window

_UNREAD_COUNT_CACHE: dict[str, dict[str, int]] = {}
_DEFAULT_OUTLOOK_STORE = "__unused__"
_SCRIPT_PATH = Path(__file__).with_name("get_outlook_unread.ps1")


def _get_unread_count_bucket(cache_data: dict[str, object], bucket_name: str) -> dict[str, int]:
    value = cache_data.get(bucket_name)
    if not isinstance(value, dict):
        raise RuntimeError(
            f"get_outlook_unread.ps1 returned invalid '{bucket_name}' data: expected a dict"
        )

    raw_counts = cast(dict[object, object], value)
    unread_counts: dict[str, int] = {}
    for key, count in raw_counts.items():
        if not isinstance(key, str) or not isinstance(count, int):
            raise RuntimeError(
                f"get_outlook_unread.ps1 returned invalid '{bucket_name}' data: "
                "expected string keys and integer counts"
            )
        unread_counts[key] = count
    return unread_counts


def _load_unread_count_cache(outlook_store: str, default_folder_ids: list[int]) -> None:
    if not _SCRIPT_PATH.exists():
        raise RuntimeError(f"Could not find Outlook unread script: {_SCRIPT_PATH}")

    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(_SCRIPT_PATH),
        "-Store",
        outlook_store,
    ]
    if default_folder_ids:
        command.extend(
            ["-DefaultFolderIds", ",".join(str(folder) for folder in default_folder_ids)]
        )

    completed = run_no_window(command)
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(
            f"get_outlook_unread.ps1 failed with exit code {completed.returncode}: {message}"
        )

    try:
        cache_data = cast(object, json.loads(completed.stdout))
    except json.JSONDecodeError as exc:
        raise RuntimeError("get_outlook_unread.ps1 returned invalid JSON") from exc

    if not isinstance(cache_data, dict):
        raise RuntimeError("get_outlook_unread.ps1 returned unexpected data")
    cache_data = cast(dict[str, object], cache_data)

    error = cache_data.get("error")
    if isinstance(error, str) and error:
        raise RuntimeError(error)

    if default_folder_ids:
        default_counts = _get_unread_count_bucket(cache_data, "default")
        _UNREAD_COUNT_CACHE["default"] = default_counts

    store_counts = _get_unread_count_bucket(cache_data, outlook_store)
    _UNREAD_COUNT_CACHE.setdefault(outlook_store, store_counts)


def get_unread_email_count(
    folders: Sequence[str | int], outlook_store: str = _DEFAULT_OUTLOOK_STORE
) -> int:
    if not isinstance(folders, list):
        raise TypeError("folders must be provided as a list")
    if outlook_store == "":
        raise ValueError("outlook_store must not be empty")
    outlook_store = outlook_store.lower()
    if outlook_store not in _UNREAD_COUNT_CACHE:
        _load_unread_count_cache(
            outlook_store,
            [folder for folder in folders if isinstance(folder, int)],
        )

    total = 0
    for folder in folders:
        if isinstance(folder, int):
            total += _UNREAD_COUNT_CACHE["default"][str(folder)]
            continue
        total += _UNREAD_COUNT_CACHE[outlook_store][folder.lower()]

    return total


def _parse_outlook_input(ctx: ProviderContext) -> tuple[list[int | str], str]:
    outlook_store = ctx.provider_config.get("outlook_store")
    if not isinstance(outlook_store, str) or not outlook_store:
        raise ValueError(
            f"[providers.{ctx.provider_name}].outlook_store must be "
            "a non-empty string when provided"
        )
    outlook_store = outlook_store.lower()

    folder_list: list[int | str] = []
    for request in ctx.requests:
        folders = request.get("folders")
        if not isinstance(folders, list) or not folders:
            raise ValueError("Outlook requests require a non-empty 'folders' list")

        for folder in folders:
            if not isinstance(folder, str) or not folder:
                raise ValueError("Outlook folder list items must be non-empty strings")
            if folder.isdigit():
                folder_list.append(int(folder))
            else:
                folder_list.append(folder)

    if not folder_list:
        raise ValueError("Outlook requests require at least one folder in 'folders'")

    return folder_list, outlook_store


class OutlookProvider:
    kind: ClassVar[str] = "outlook"

    def count(self, ctx: ProviderContext) -> int:
        folder_list, outlook_store = _parse_outlook_input(ctx)
        return get_unread_email_count(folder_list, outlook_store=outlook_store)


provider_registry.register_count_provider(OutlookProvider)
