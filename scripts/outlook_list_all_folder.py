import time

from win32com.client import gencache

DEFAULT_FOLDERS = [
    (6, "Inbox"),
    (5, "Sent"),
    (4, "Outbox"),
    (3, "Deleted"),
    (16, "Drafts"),
    (23, "Junk"),
    (9, "Calendar"),
    (10, "Contacts"),
    (13, "Tasks"),
    (11, "Journal"),
    (12, "Notes"),
]


def print_folder(folder, indent=""):
    unread = 0
    try:
        unread = folder.UnReadItemCount
    except Exception:
        unread = 0

    print(f"{indent}{folder.Name} | Unread : {unread}")

    try:
        for i in range(1, folder.Folders.Count + 1):
            print_folder(folder.Folders.Item(i), "  " + indent)
    except Exception:
        pass


def main():
    outlook = gencache.EnsureDispatch("Outlook.Application")
    namespace = outlook.GetNamespace("MAPI")

    print("---- Default Folders (use numeric ID) -------------------------------")

    for folder_id, name in DEFAULT_FOLDERS:
        try:
            folder = namespace.GetDefaultFolder(folder_id)
            unread = folder.UnReadItemCount
            print(f"  ID {folder_id} : {name} | Unread: {unread}")
        except Exception:
            pass

    for i in range(1, namespace.Folders.Count + 1):
        store = namespace.Folders.Item(i)
        started_at = time.perf_counter()
        print(f'---- Store: "{store.Name}" --------------------------------------')
        for j in range(1, store.Folders.Count + 1):
            print_folder(store.Folders.Item(j))
        elapsed = time.perf_counter() - started_at
        print(f'---- Store: "{store.Name}" | Elapsed: {elapsed:.2f}s ----------------')

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
