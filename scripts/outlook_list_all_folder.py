from win32com.client import gencache


DEFAULT_FOLDERS = [
    {"Id": 6, "Name": "Inbox"},
    {"Id": 5, "Name": "Sent"},
    {"Id": 4, "Name": "Outbox"},
    {"Id": 3, "Name": "Deleted"},
    {"Id": 16, "Name": "Drafts"},
    {"Id": 23, "Name": "Junk"},
    {"Id": 9, "Name": "Calendar"},
    {"Id": 10, "Name": "Contacts"},
    {"Id": 13, "Name": "Tasks"},
    {"Id": 11, "Name": "Journal"},
    {"Id": 12, "Name": "Notes"},
]


def get_folder_info(folder, indent=""):
    unread = 0
    try:
        unread = folder.UnReadItemCount
    except Exception:
        unread = 0

    print(f"{indent}{folder.Name} | Unread : {unread}")

    try:
        subfolders = folder.Folders
        for index in range(1, subfolders.Count + 1):
            get_folder_info(subfolders.Item(index), f"  {indent}")
    except Exception:
        pass


def main():
    outlook = gencache.EnsureDispatch("Outlook.Application")
    namespace = outlook.GetNamespace("MAPI")

    print("---- Default Folders (use numeric ID) -------------------------------")

    for item in DEFAULT_FOLDERS:
        try:
            folder = namespace.GetDefaultFolder(item["Id"])
            unread = folder.UnReadItemCount
            print(f"  ID {item['Id']} : {item['Name']} | Unread: {unread}")
        except Exception:
            pass

    default_store = namespace.Folders.Item(1)
    stores = namespace.Folders

    for store_index in range(1, stores.Count + 1):
        store = stores.Item(store_index)
        print(f"---- Store: {store.Name} --------------------------------------")
        folders = default_store.Folders
        for folder_index in range(1, folders.Count + 1):
            get_folder_info(folders.Item(folder_index))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
