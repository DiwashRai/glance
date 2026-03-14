[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-FolderRecord {
    param(
        [Parameter(Mandatory = $true)]
        $Folder,

        [int]$DefaultFolderId = 0
    )

    [pscustomobject]@{
        DefaultFolderId = $DefaultFolderId
        Store           = $Folder.Store.DisplayName
        Path            = $Folder.FolderPath
        Name            = $Folder.Name
        UnreadCount     = [int]$Folder.UnReadItemCount
        ItemCount       = [int]$Folder.Items.Count
    }
}

function Add-FolderTree {
    param(
        [Parameter(Mandatory = $true)]
        $Folder,

        [Parameter(Mandatory = $true)]
        [System.Collections.Generic.HashSet[string]]$SeenEntryIds,

        [Parameter(Mandatory = $true)]
        [System.Collections.Generic.List[object]]$Results
    )

    $entryId = [string]$Folder.EntryID
    if (-not [string]::IsNullOrWhiteSpace($entryId) -and -not $SeenEntryIds.Add($entryId)) {
        return
    }

    $Results.Add((Get-FolderRecord -Folder $Folder))

    foreach ($childFolder in @($Folder.Folders)) {
        Add-FolderTree -Folder $childFolder -SeenEntryIds $SeenEntryIds -Results $Results
    }
}

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

$outlook = New-Object -ComObject Outlook.Application
$namespace = $outlook.GetNamespace("MAPI")
$seenEntryIds = [System.Collections.Generic.HashSet[string]]::new()
$defaultResults = [System.Collections.Generic.List[object]]::new()
$otherResults = [System.Collections.Generic.List[object]]::new()

foreach ($defaultFolder in $defaultFolders) {
    try {
        $folder = $namespace.GetDefaultFolder($defaultFolder.Id)
        if ($null -ne $folder) {
            $entryId = [string]$folder.EntryID
            if ([string]::IsNullOrWhiteSpace($entryId) -or $seenEntryIds.Add($entryId)) {
                $defaultResults.Add(
                    (Get-FolderRecord -Folder $folder -DefaultFolderId $defaultFolder.Id)
                )
            }
        }
    } catch {
        continue
    }
}

foreach ($rootFolder in @($namespace.Folders)) {
    Add-FolderTree -Folder $rootFolder -SeenEntryIds $seenEntryIds -Results $otherResults
}

$defaultResults
$otherResults | Sort-Object Store, Path
