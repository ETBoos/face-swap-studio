[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Installer,
    [string]$PythonExe = ".venv\Scripts\python.exe",
    [string]$FrameTestScript = ""
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot
$TestRoot = Join-Path ([IO.Path]::GetTempPath()) ("fss-camera-test-" + [guid]::NewGuid())
$InstallDir = Join-Path $TestRoot "Camera Component"
$ReportsDir = Join-Path $ProjectRoot "build\reports"
$CameraClasses = @(
    @{ View = [Microsoft.Win32.RegistryView]::Registry64; Id = "{E3B79076-C56E-4E15-95B9-4B6F523A0010}"; Dll = "FaceSwapStudioCamera64.dll" },
    @{ View = [Microsoft.Win32.RegistryView]::Registry64; Id = "{E3B79076-C56E-4E15-95B9-4B6F523A0011}"; Dll = "FaceSwapStudioCamera64.dll" },
    @{ View = [Microsoft.Win32.RegistryView]::Registry32; Id = "{E3B79076-C56E-4E15-95B9-4B6F523A0020}"; Dll = "FaceSwapStudioCamera32.dll" },
    @{ View = [Microsoft.Win32.RegistryView]::Registry32; Id = "{E3B79076-C56E-4E15-95B9-4B6F523A0021}"; Dll = "FaceSwapStudioCamera32.dll" }
)
function Get-CameraServer {
    param($CameraClass)
    $BaseKey = [Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::LocalMachine, $CameraClass.View)
    try {
        $Key = $BaseKey.OpenSubKey("SOFTWARE\Classes\CLSID\$($CameraClass.Id)\InprocServer32")
        if ($Key) { try { return $Key.GetValue("") } finally { $Key.Dispose() } }
        return $null
    }
    finally { $BaseKey.Dispose() }
}
function Invoke-CameraInstaller {
    param([string]$Program, [string[]]$CommandArguments)
    $Process = Start-Process -FilePath $Program -ArgumentList $CommandArguments -PassThru
    if (-not $Process.WaitForExit(120000)) { $Process.Kill(); throw "Camera installer timed out." }
    if ($Process.ExitCode -ne 0) { throw "Camera installer failed with exit code $($Process.ExitCode)." }
}
$Installed = $false
try {
    foreach ($CameraClass in $CameraClasses) {
        if (Get-CameraServer $CameraClass) { throw "A FaceSwap Studio camera is already installed. Use a clean Windows runner." }
    }
    New-Item -ItemType Directory -Force -Path $InstallDir, $ReportsDir | Out-Null
    Invoke-CameraInstaller (Resolve-Path $Installer).Path @(
        "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-",
        "/DIR=`"$InstallDir`"", "/LOG=`"$ReportsDir\camera-install.log`""
    )
    $Installed = $true
    foreach ($CameraClass in $CameraClasses) {
        $Expected = Join-Path $InstallDir $CameraClass.Dll
        if ((Get-CameraServer $CameraClass) -ne $Expected) { throw "Camera registration mismatch for $($CameraClass.Id)." }
    }
    if ($FrameTestScript) {
        $FrameScriptPath = (Resolve-Path $FrameTestScript).Path
        $FrameProcess = Start-Process -FilePath (Get-Command $PythonExe).Source -ArgumentList @("`"$FrameScriptPath`"") -WorkingDirectory $ProjectRoot -PassThru -RedirectStandardOutput "$ReportsDir\camera-frame-test.txt" -RedirectStandardError "$ReportsDir\camera-frame-test-stderr.txt"
        if (-not $FrameProcess.WaitForExit(45000)) {
            $FrameProcess.Kill()
            throw "Virtual camera frame test exceeded 45 seconds."
        }
        if ($FrameProcess.ExitCode -ne 0) { throw "Virtual camera frame test failed with exit code $($FrameProcess.ExitCode)." }
    }
    Invoke-CameraInstaller (Join-Path $InstallDir "unins000.exe") @(
        "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/LOG=`"$ReportsDir\camera-uninstall.log`""
    )
    $Installed = $false
    foreach ($CameraClass in $CameraClasses) {
        if (Get-CameraServer $CameraClass) { throw "Camera uninstaller left CLSID $($CameraClass.Id)." }
    }
    @{ passed = $true; registry_views = @("x64", "x86"); frame_test_executed = [bool]$FrameTestScript; receiving_app_compatibility_tested = $false } |
        ConvertTo-Json | Set-Content "$ReportsDir\camera-installer-test.json" -Encoding utf8
    Remove-Item $TestRoot -Recurse -Force
}
finally {
    if ($Installed -and (Test-Path (Join-Path $InstallDir "unins000.exe"))) {
        Invoke-CameraInstaller (Join-Path $InstallDir "unins000.exe") @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART")
    }
    Pop-Location
}
