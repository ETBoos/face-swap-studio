# Pro mode: locate DeepFaceLive (NVIDIA preferred) and stage a .dfm into userdata\dfm_models
# Usage:
#   .\scripts\setup-deepfacelive-win.ps1 -DeepFaceLiveRoot "C:\DeepFaceLive_NVIDIA" -DfmPath "D:\models\person.dfm"
param(
  [string]$DeepFaceLiveRoot = $env:DEEPFACELIVE_ROOT,
  [Parameter(Mandatory = $true)][string]$DfmPath,
  [string]$UserdataDir
)

$ErrorActionPreference = "Stop"

function Find-DflRoot {
  param([string]$Hint)
  $candidates = @()
  if ($Hint) { $candidates += $Hint }
  $candidates += @(
    "C:\DeepFaceLive_NVIDIA",
    "C:\DeepFaceLive",
    "$env:USERPROFILE\DeepFaceLive_NVIDIA",
    "$env:USERPROFILE\DeepFaceLive"
  )
  foreach ($c in $candidates) {
    if (-not $c) { continue }
    if ((Test-Path (Join-Path $c "DeepFaceLive.bat")) -or (Test-Path (Join-Path $c "main.py"))) {
      return (Resolve-Path $c).Path
    }
  }
  return $null
}

$root = Find-DflRoot -Hint $DeepFaceLiveRoot
if (-not $root) {
  Write-Error "未找到 DeepFaceLive。请安装 NVIDIA 构建并传入 -DeepFaceLiveRoot，或设置 DEEPFACELIVE_ROOT。"
}

if (-not (Test-Path $DfmPath) -or [IO.Path]::GetExtension($DfmPath).ToLower() -ne ".dfm") {
  Write-Error "无效 .dfm：$DfmPath"
}

$ud = if ($UserdataDir) { $UserdataDir } else { Join-Path $root "userdata" }
$models = Join-Path $ud "dfm_models"
New-Item -ItemType Directory -Force -Path $models | Out-Null
$dest = Join-Path $models (Split-Path $DfmPath -Leaf)
Copy-Item -Force $DfmPath $dest

Write-Host "DeepFaceLive root: $root"
Write-Host "Staged model: $dest"
Write-Host "提示：.dfm 须与导出它的 DeepFaceLab/DeepFaceLive 版本匹配；RTX 优先用 NVIDIA 构建。"
Write-Host "启动后在 Face swapper 中选择该模型。可用："
Write-Host "  cd `"$root`"; .\DeepFaceLive.bat"
Write-Host "或由壳传入 deepfacelive_root=$root dfm_path=$DfmPath"
