import argparse


def get_unread_email_count(folders):
    try:
        import win32com.client
    except ImportError as exc:
        raise RuntimeError("pywin32 is required for Outlook COM access") from exc

    if not isinstance(folders, list) or not folders:
        raise ValueError("folders must be a non-empty list of Outlook folder names")

    normalized_targets = {folder.strip().lower() for folder in folders if folder.strip()}
    if not normalized_targets:
        raise ValueError("folders must contain at least one non-empty folder name")

    outlook = win32com.client.Dispatch("Outlook.Application")
    namespace = outlook.GetNamespace("MAPI")
    total = 0
    matched_paths = set()
    stack = list(namespace.Folders)

    while stack:
        folder = stack.pop()
        folder_name = str(folder.Name).strip().lower()
        folder_path = str(folder.FolderPath).strip().lower()

        if folder_name in normalized_targets or folder_path in normalized_targets:
            total += int(folder.UnReadItemCount)
            matched_paths.add(folder_name)
            matched_paths.add(folder_path)

        stack.extend(list(folder.Folders))

    missing_folders = normalized_targets - matched_paths
    if missing_folders:
        raise ValueError(
            f"Could not find Outlook folder(s): {', '.join(sorted(missing_folders))}"
        )

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
