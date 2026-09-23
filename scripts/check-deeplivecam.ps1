# FaceSwap Studio — check a local Deep-Live-Cam checkout (no download).
# Usage: powershell -File scripts\check-deeplivecam.ps1 -Root C:\Deep-Live-Cam
param(
    [string]$Root = $env:DEEP_LIVE_CAM_ROOT
)

$ErrorActionPreference = "Stop"

if (-not $Root) {
    Write-Host "Set DEEP_LIVE_CAM_ROOT or pass -Root. Need run.py and modules\core.py."
    exit 1
}

$rootPath = Resolve-Path -LiteralPath $Root
$runPy = Join-Path $rootPath "run.py"
$core = Join-Path $rootPath "modules\core.py"
$pyWin = Join-Path $rootPath "venv\Scripts\python.exe"
$pyNix = Join-Path $rootPath "venv\bin\python"

Write-Host "Deep-Live-Cam root: $rootPath"
if (-not (Test-Path -LiteralPath $runPy)) { Write-Host "MISSING run.py"; exit 1 }
if (-not (Test-Path -LiteralPath $core)) { Write-Host "MISSING modules\core.py"; exit 1 }
Write-Host "OK layout (run.py + modules\core.py)"

$python = $null
if (Test-Path -LiteralPath $pyWin) { $python = $pyWin }
elseif (Test-Path -LiteralPath $pyNix) { $python = $pyNix }
elseif ($env:DEEP_LIVE_CAM_PYTHON) { $python = $env:DEEP_LIVE_CAM_PYTHON }

if (-not $python) {
    Write-Host "MISSING venv python. Create DLC's venv or set DEEP_LIVE_CAM_PYTHON."
    exit 1
}
Write-Host "Python: $python"

$ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
if (-not $ffmpeg) {
    Write-Host "WARN ffmpeg not on PATH. DLC pre_check refuses to run without it."
} else {
    Write-Host "OK ffmpeg: $($ffmpeg.Source)"
}

$models = Join-Path $rootPath "models"
$fp32 = Join-Path $models "inswapper_128.onnx"
$fp16 = Join-Path $models "inswapper_128_fp16.onnx"
if ((Test-Path -LiteralPath $fp32) -or (Test-Path -LiteralPath $fp16)) {
    Write-Host "OK inswapper model present"
} else {
    Write-Host "WARN inswapper model not in models\. DLC may download it on first run."
}

Write-Host "Layout check finished. This does not run a face swap and does not prove a camera frame."
exit 0
