[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Installer,
    [string]$PythonExe = ".venv\Scripts\python.exe"
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot
$TestRoot = Join-Path ([IO.Path]::GetTempPath()) ("fss-installer-test-" + [guid]::NewGuid())
$InstallDir = Join-Path $TestRoot "Installed App"
$DataMarker = Join-Path $TestRoot "userdata\keep.txt"
$ReportsDir = Join-Path $ProjectRoot "build\reports"
$UninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{E79E9B04-BFC1-41CB-9609-D15B02BA68AE}_is1"
function Invoke-InstallerProcess {
    param([string]$Program, [string[]]$CommandArguments)
    $Process = Start-Process -FilePath $Program -ArgumentList $CommandArguments -PassThru
    if (-not $Process.WaitForExit(120000)) {
        $Process.Kill()
        throw "Installer timed out: $Program"
    }
    if ($Process.ExitCode -ne 0) { throw "Installer failed: $Program (exit $($Process.ExitCode))" }
}
try {
    if (Test-Path $UninstallKey) {
        throw "An installed FaceSwap Studio exists. Run this test on a clean Windows runner."
    }
    New-Item -ItemType Directory -Force -Path $InstallDir, (Split-Path $DataMarker), $ReportsDir | Out-Null
    Set-Content $DataMarker "User data must survive uninstall."
    $Installer = (Resolve-Path $Installer).Path
    Invoke-InstallerProcess $Installer @(
        "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-",
        "/DIR=`"$InstallDir`"", "/LOG=`"$ReportsDir\install.log`""
    )
    $InstalledExe = Join-Path $InstallDir "FaceSwapStudio.exe"
    if (-not (Test-Path $InstalledExe)) { throw "Installer did not install the executable." }
    & $PythonExe "scripts\smoke-windows-package.py" $InstalledExe --report "$ReportsDir\installed-smoke.json" --data-dir (Split-Path $DataMarker)
    if ($LASTEXITCODE -ne 0) { throw "Installed application smoke test failed." }
    $StartShortcut = Join-Path ([Environment]::GetFolderPath("Programs")) "FaceSwap Studio\FaceSwap Studio.lnk"
    if (-not (Test-Path $StartShortcut)) { throw "Start menu shortcut was not created." }
    Invoke-InstallerProcess (Join-Path $InstallDir "unins000.exe") @(
        "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/LOG=`"$ReportsDir\uninstall.log`""
    )
    if (Test-Path $InstalledExe) { throw "Uninstaller left the application executable." }
    if (Test-Path $StartShortcut) { throw "Uninstaller left the start menu shortcut." }
    if (-not (Test-Path $DataMarker)) { throw "Uninstaller removed external user data." }
    @{ passed = $true; install = $true; launch = $true; uninstall = $true; retained_external_data = $true } |
        ConvertTo-Json | Set-Content "$ReportsDir\installer-test.json" -Encoding utf8
    Remove-Item $TestRoot -Recurse -Force
}
finally { Pop-Location }
