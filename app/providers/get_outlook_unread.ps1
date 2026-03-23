
<#
.SYNOPSIS
Returns unread Outlook item counts for a named store and optional default folder IDs as JSON.

.DESCRIPTION
Queries Outlook via COM and returns unread item counts as JSON for the specified store.
It can also include unread counts for optional default folder IDs such as Inbox and Junk.

Example output:
{
  "default": {
    "6": 1,
    "23": 21
  },
  "jane.doe@outlook.com": {
    "inbox": 1,
    "personal": 2
    "urgent": 4,
  }
}

.PARAMETER Store
The Outlook store display name to query. Matching is case-insensitive.

.PARAMETER DefaultFolderIds
Optional comma-separated list of Outlook default folder IDs to include in the output.
Some examples are 6=Inbox and 23=Junk.

.EXAMPLE
.\get_outlook_unread.ps1 -Store "jane.doe@outlook.com"

.EXAMPLE
.\get_outlook_unread.ps1 -Store "jane.doe@outlook.com" -DefaultFolderIds "6,23"
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$Store,

    [string]$DefaultFolderIds = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Main {
    try {
        $outlook = New-Object -ComObject Outlook.Application
        $namespace = $outlook.GetNamespace("MAPI")

        $result = [ordered]@{}

        # get default folder id counts
        $ids = $DefaultFolderIds -split ',' | Where-Object { $_ -match '^\d+$' }
        if ($ids) {
            $defaults = [ordered]@{}
            foreach ($id in $ids) {
                try   { $defaults[$id] = [int]$namespace.GetDefaultFolder([int]$id).UnReadItemCount }
                catch { $defaults[$id] = -1 }
            }
            $result["default"] = $defaults
        }

        # locate correct store
        $storeRoot = $null
        foreach ($root in $namespace.Folders) {
            if ($root.Name -ieq $Store) { $storeRoot = $root; break }
        }
        if ($null -eq $storeRoot) {
            Write-Output (ConvertTo-Json @{ error = "Store not found: $Store" })
            return
        }

        $folders = [ordered]@{}
        $stack   = [System.Collections.Generic.Stack[object]]::new()
        foreach ($f in $storeRoot.Folders) { $stack.Push(@{ f = $f; p = $f.Name.ToLower() }) }

        while ($stack.Count -gt 0) {
            $item = $stack.Pop()
            try {
                $folders[$item.p] = [int]$item.f.UnreadItemCount
                foreach ($sub in $item.f.Folders) {
                    $stack.Push(@{ f = $sub; p = "$($item.p)/$($sub.Name.ToLower())" })
                }
            } catch {}
        }

        $result[$Store.ToLower()] = $folders
        Write-Output (ConvertTo-Json $result)
    }

    catch {
        Write-Output (ConvertTo-Json @{ error = $_.Exception.Message })
    }
}

Main
