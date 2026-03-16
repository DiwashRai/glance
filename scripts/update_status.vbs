Dim shell, scriptDir, cmd

Set shell = CreateObject("WScript.Shell")
scriptDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
cmd = Chr(34) & scriptDir & "\update_status.cmd" & Chr(34)

shell.Run cmd, 0, False

Set shell = Nothing
