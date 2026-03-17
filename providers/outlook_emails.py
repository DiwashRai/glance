import argparse
from win32com.client import gencache


_UNREAD_COUNT_CACHE = {}


def _make_cache_key(store_name, folder_identifier):
    return f"{store_name}::{folder_identifier}"


def _get_unread_count_for_folder(folder, store):
    store_name = str(store.Name)
    cache_key = _make_cache_key(store_name, folder)
    if cache_key in _UNREAD_COUNT_CACHE:
        return _UNREAD_COUNT_CACHE[cache_key]

    def walk_until_found(current_folder):
        folder_name = str(current_folder.Name)
        unread_count = int(current_folder.UnReadItemCount)

        name_key = _make_cache_key(store_name, folder_name)
        _UNREAD_COUNT_CACHE.setdefault(name_key, unread_count)

        if folder == folder_name:
            return unread_count

        child_folders = current_folder.Folders
        for index in range(1, child_folders.Count + 1):
            found_count = walk_until_found(child_folders.Item(index))
            if found_count is not None:
                return found_count
        return None

    root_folders = store.Folders
    for index in range(1, root_folders.Count + 1):
        found_count = walk_until_found(root_folders.Item(index))
        if found_count is not None:
            return found_count

    raise ValueError(f"Could not find Outlook folder: {folder}")


def get_unread_email_count(folders, outlook_store=None):
    if not isinstance(folders, list):
        raise TypeError("folders must be provided as a list")
    if outlook_store is not None and not isinstance(outlook_store, str):
        raise TypeError("outlook_store must be a string when provided")
    if outlook_store == "":
        raise ValueError("outlook_store must not be an empty string")

    outlook = gencache.EnsureDispatch("Outlook.Application")
    namespace = outlook.GetNamespace("MAPI")

    if len(folders) == 1 and isinstance(folders[0], int):
        return int(namespace.GetDefaultFolder(folders[0]).UnReadItemCount)

    store = None
    if any(isinstance(folder, str) for folder in folders):
        if outlook_store is None:
            raise ValueError("outlook_store is required when folders include names")
        for index in range(1, namespace.Folders.Count + 1):
            candidate = namespace.Folders.Item(index)
            if str(candidate.Name) == outlook_store:
                store = candidate
                break
        if store is None:
            raise ValueError(f"Could not find Outlook store: {outlook_store}")

    total = 0
    get_default_folder = namespace.GetDefaultFolder
    for folder in folders:
        if isinstance(folder, int):
            total += int(get_default_folder(folder).UnReadItemCount)
            continue

        if isinstance(folder, str):
            total += _get_unread_count_for_folder(folder, store)
            continue

        raise TypeError("Outlook folders must be strings or integers")

    return total


# ---- Helpers ------------------------------------------------------------------------------------


def parse_folder_arg(value):
    return int(value) if value.isdigit() else value


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Return unread counts for Outlook folders via COM."
    )
    parser.add_argument("folders", nargs="+", help="Folder names or Outlook folder paths.")
    parser.add_argument(
        "--outlook-store",
        help="Required when folder names are provided; Outlook store name to search.",
    )
    args = parser.parse_args(argv)
    args.folders = [parse_folder_arg(folder) for folder in args.folders]
    if any(isinstance(folder, str) for folder in args.folders) and not args.outlook_store:
        parser.error("--outlook-store is required when folder names are provided.")
    return args


def main(argv=None):
    args = parse_args(argv)
    print(get_unread_email_count(args.folders, outlook_store=args.outlook_store))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
