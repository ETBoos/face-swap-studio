[CmdletBinding()]
param(
    [string]$PythonExe = ".venv\Scripts\python.exe",
    [string]$InnoSetupCompiler = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw "Windows builds must run on Windows x64. Use the Windows package GitHub Actions workflow."
}

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot
function Invoke-Checked {
    param([string]$Program, [string[]]$CommandArguments)
    & $Program @CommandArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $Program $CommandArguments"
    }
}

$SavedQtPlatform = $env:QT_QPA_PLATFORM
try {
    $PythonExe = (Get-Command $PythonExe -ErrorAction Stop).Source
    $ReportsDir = Join-Path $ProjectRoot "build\reports"
    $MetadataDir = Join-Path $ProjectRoot "build\packaging"
    $BundleDir = Join-Path $ProjectRoot "dist\FaceSwapStudio"
    $ArtifactsDir = Join-Path $ProjectRoot "dist\artifacts"
    New-Item -ItemType Directory -Force -Path $ReportsDir, $MetadataDir, $ArtifactsDir | Out-Null
    Invoke-Checked $PythonExe @("-c", "import struct, sys; assert sys.platform == 'win32' and struct.calcsize('P') == 8, '64-bit Windows Python required'")
    if (-not $InnoSetupCompiler) {
        $CompilerCommand = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
        if ($CompilerCommand) { $InnoSetupCompiler = $CompilerCommand.Source }
        else {
            foreach ($Candidate in @(
                "${env:ProgramFiles}\Inno Setup 7\ISCC.exe",
                "${env:ProgramFiles(x86)}\Inno Setup 7\ISCC.exe",
                "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
            )) {
                if (Test-Path $Candidate) { $InnoSetupCompiler = $Candidate; break }
            }
        }
    }
    if (-not $InnoSetupCompiler -or -not (Test-Path $InnoSetupCompiler)) {
        throw "Install Inno Setup or supply -InnoSetupCompiler with the full path to ISCC.exe."
    }
    # A failed build must never leave old artifacts that look like a new delivery.
    Get-ChildItem $ArtifactsDir -File | Remove-Item -Force
    $env:QT_QPA_PLATFORM = "offscreen"
    Invoke-Checked $PythonExe @("-m", "pytest", "-q", "--junitxml=$ReportsDir\tests.xml")
    Invoke-Checked $PythonExe @("scripts\prepare-windows-package.py")
    $Version = (Get-Content (Join-Path $MetadataDir "version.txt") -Raw).Trim()
    $VsWhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path $VsWhere)) { throw "Visual Studio Build Tools with C++ support is required." }
    $MSBuild = & $VsWhere -latest -products * -requires Microsoft.Component.MSBuild -find "MSBuild\**\Bin\MSBuild.exe" | Select-Object -First 1
    if (-not $MSBuild) { throw "MSBuild was not found." }
    $NativeDir = Join-Path $ProjectRoot "build\native"
    foreach ($Platform in @("x64", "Win32")) {
        $NativeOutput = (Join-Path $NativeDir $Platform).Replace('\', '/') + '/'
        $NativeIntermediate = (Join-Path $NativeDir "obj\$Platform").Replace('\', '/') + '/'
        Invoke-Checked $MSBuild @(
            "native\virtual_camera\UnityCaptureFilter.vcxproj", "/m", "/nologo",
            "/p:Configuration=Release", "/p:Platform=$Platform", "/p:PlatformToolset=v143",
            "/p:WindowsTargetPlatformVersion=10.0", "/p:OutDir=$NativeOutput", "/p:IntDir=$NativeIntermediate",
            "/flp:logfile=$ReportsDir\camera-$Platform-build.log;verbosity=normal"
        )
    }
    Invoke-Checked $InnoSetupCompiler @("/DAppVersion=$Version", "/DNativeDir=$NativeDir", "/DArtifactsDir=$ArtifactsDir", "packaging\camera-installer.iss")
    Invoke-Checked $PythonExe @("-m", "PyInstaller", "--clean", "--noconfirm", "--distpath", "dist", "--workpath", "build\pyinstaller", "packaging\face-swap-studio.spec")
    foreach ($WorkerFile in @("facefusion_worker.py", "facefusion_protocol.py")) {
        if (-not (Test-Path (Join-Path $BundleDir "_internal\face_swap_studio\engines\$WorkerFile"))) {
            throw "The external FaceFusion worker source was not bundled: $WorkerFile"
        }
    }
    $ComponentsDir = Join-Path $BundleDir "components"
    New-Item -ItemType Directory -Force -Path $ComponentsDir | Out-Null
    Copy-Item (Join-Path $ArtifactsDir "FaceSwapStudio-Camera-Setup.exe") $ComponentsDir
    Copy-Item "packaging\README-WINDOWS.txt" $BundleDir
    Copy-Item (Join-Path $MetadataDir "THIRD-PARTY-NOTICES") $BundleDir -Recurse -Force
    Copy-Item (Join-Path $MetadataDir "build-info.json") $BundleDir
    Copy-Item (Join-Path $MetadataDir "activation.json") $BundleDir
    $UnexpectedModels = @(Get-ChildItem $BundleDir -Recurse -File | Where-Object {
        $_.Extension -in @(".onnx", ".dfm", ".pth", ".pt", ".safetensors")
    })
    if ($UnexpectedModels.Count -gt 0) {
        throw "Model files were unexpectedly bundled. Review provenance before packaging."
    }
    Invoke-Checked $PythonExe @("scripts\smoke-windows-package.py", "$BundleDir\FaceSwapStudio.exe", "--report", "$ReportsDir\portable-smoke.json")
    Invoke-Checked $InnoSetupCompiler @("/DAppVersion=$Version", "/DBundleDir=$BundleDir", "/DArtifactsDir=$ArtifactsDir", "packaging\windows-installer.iss")
    $PortablePath = Join-Path $ArtifactsDir "FaceSwapStudio-$Version-windows-x64-portable.zip"
    Invoke-Checked $PythonExe @("-c", "import shutil,sys; shutil.make_archive(sys.argv[1], 'zip', root_dir='dist', base_dir='FaceSwapStudio')", ($PortablePath -replace '\.zip$', ''))
    Copy-Item (Join-Path $MetadataDir "build-info.json") $ArtifactsDir
    $Checksums = Get-ChildItem $ArtifactsDir -File | Sort-Object Name | ForEach-Object {
        $Hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        "$Hash  $($_.Name)"
    }
    $Checksums | Set-Content (Join-Path $ArtifactsDir "SHA256SUMS.txt") -Encoding ascii
    Write-Host "Windows package complete: $ArtifactsDir"
    Write-Host "This build verifies package startup only; GPU quality and call compatibility require real hardware."
}
finally {
    $env:QT_QPA_PLATFORM = $SavedQtPlatform
    Pop-Location
}
