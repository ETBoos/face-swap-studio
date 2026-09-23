# ASCII-only so Windows PowerShell 5.1 does not mis-read UTF-8.
# Shortcut display name: U+6253 U+5F00 U+6362 U+8138
param(
    [Parameter(Mandatory = $true)][string]$TargetBat,
    [Parameter(Mandatory = $true)][string]$WorkingDirectory
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $TargetBat)) {
    throw "launcher not found: $TargetBat"
}
$desktop = [Environment]::GetFolderPath('Desktop')
if ([string]::IsNullOrWhiteSpace($desktop)) {
    throw 'Desktop folder not found'
}
$name = -join @([char]0x6253, [char]0x5F00, [char]0x6362, [char]0x8138)
$lnkPath = Join-Path $desktop ($name + '.lnk')
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($lnkPath)
$shortcut.TargetPath = Join-Path $env:SystemRoot 'System32\cmd.exe'
$shortcut.Arguments = '/c ""' + $TargetBat + '""'
$shortcut.WorkingDirectory = $WorkingDirectory
$shortcut.WindowStyle = 1
$shortcut.Description = 'FaceSwap Studio'
$shortcut.Save()
Write-Output $lnkPath
