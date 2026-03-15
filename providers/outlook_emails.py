import argparse


def get_unread_email_count(folders):
    if not isinstance(folders, list):
        raise TypeError("folders must be provided as a list")

    try:
        from win32com.client import gencache
    except ImportError as exc:
        raise RuntimeError("pywin32 is required for Outlook COM access") from exc

    outlook = gencache.EnsureDispatch("Outlook.Application")
    namespace = outlook.GetNamespace("MAPI")
    named_folder_counts = {}

    def walk(folder):
        folder_name = str(folder.Name)
        folder_path = str(folder.FolderPath)
        unread_count = int(folder.UnReadItemCount)

        named_folder_counts[folder_name] = named_folder_counts.get(folder_name, 0) + unread_count
        named_folder_counts[folder_path] = named_folder_counts.get(folder_path, 0) + unread_count

        child_folders = folder.Folders
        for index in range(1, child_folders.Count + 1):
            walk(child_folders.Item(index))

    for index in range(1, namespace.Folders.Count + 1):
        walk(namespace.Folders.Item(index))

    get_default_folder = namespace.GetDefaultFolder
    total = 0
    for folder in folders:
        if isinstance(folder, int):
            total += int(get_default_folder(folder).UnReadItemCount)
            continue

        if isinstance(folder, str):
            if folder not in named_folder_counts:
                raise ValueError(f"Could not find Outlook folder: {folder}")
            total += named_folder_counts[folder]
            continue

        raise TypeError("Outlook folders must be strings or integers")

    return total


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Return unread counts for Outlook folders via COM."
    )
    parser.add_argument("folders", nargs="+", help="Folder names or Outlook folder paths.")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    print(get_unread_email_count(args.folders))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
