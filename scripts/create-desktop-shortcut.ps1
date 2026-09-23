# ASCII-only so Windows PowerShell 5.1 does not mis-read UTF-8.
# Shortcut display name: U+6253 U+5F00 U+6362 U+8138
# Target is pythonw.exe so the GUI is not attached to a console.
# Closing a terminal must not close Studio. WindowStyle 7 keeps the
# shortcut from restoring a console window.
# Failures write [错误] and exit 1 so the calling bat can pause.
param(
    [Parameter(Mandatory = $true)][string]$WorkingDirectory,
    [string]$Pythonw = ""
)
$ErrorActionPreference = 'Stop'
try {
    if ([string]::IsNullOrWhiteSpace($Pythonw)) {
        $Pythonw = Join-Path $WorkingDirectory ".venv\Scripts\pythonw.exe"
    }
    if (-not (Test-Path -LiteralPath $Pythonw)) {
        throw "pythonw.exe not found: $Pythonw"
    }
    $desktop = [Environment]::GetFolderPath('Desktop')
    if ([string]::IsNullOrWhiteSpace($desktop)) {
        throw "Desktop folder not found"
    }
    $name = -join @([char]0x6253, [char]0x5F00, [char]0x6362, [char]0x8138)
    $lnkPath = Join-Path $desktop ($name + '.lnk')
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($lnkPath)
    $shortcut.TargetPath = $Pythonw
    $shortcut.Arguments = "-m face_swap_studio"
    $shortcut.WorkingDirectory = $WorkingDirectory
    $shortcut.WindowStyle = 7
    $shortcut.Description = "FaceSwap Studio"
    $shortcut.Save()
    Write-Output $lnkPath
    exit 0
} catch {
    Write-Host "[错误] $($_.Exception.Message)"
    exit 1
}
