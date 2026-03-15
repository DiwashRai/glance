
$defaultFolders = @(
    @{ Id = 6;  Name = "Inbox" },
    @{ Id = 5;  Name = "Sent" },
    @{ Id = 4;  Name = "Outbox" },
    @{ Id = 3;  Name = "Deleted" },
    @{ Id = 16; Name = "Drafts" },
    @{ Id = 23; Name = "Junk" },
    @{ Id = 9;  Name = "Calendar" },
    @{ Id = 10; Name = "Contacts" },
    @{ Id = 13; Name = "Tasks" },
    @{ Id = 11; Name = "Journal" },
    @{ Id = 12; Name = "Notes" }
)

function Get-FolderInfo {
    param($folder, $indent = "")

    $unread = 0
    try {
        $unread = $folder.UnReadItemCount
    } catch {
        $unread = 0
    }

    Write-Output "$indent$($folder.Name) | Unread : $unread"

    try {
        foreach ($subfolder in $folder.Folders) {
            Get-FolderInfo -folder $subfolder -indent "  $indent"
        }
    } catch {
    }
}


$outlook = New-Object -ComObject Outlook.Application
$namespace = $outlook.GetNamespace("MAPI")

Write-Output "---- Default Folders (use numeric ID) -------------------------------"

foreach ($item in $defaultFolders) {
    try {
        $folder = $namespace.GetDefaultFolder($item.ID)
        $unread = $folder.UnReadItemCount
        Write-Output "  ID $($item.ID) : $($item.Name) | Unread: $unread"
    } catch {
    }
}

$defaultStore = $namespace.Folders.Item(1)

Write-Output "---- All folders (use quoted folder name) ---------------------------"

foreach ($folder in $defaultStore.Folders) {
    Get-FolderInfo -folder $folder
}

$defaultResults
$otherResults | Sort-Object Store, Path
