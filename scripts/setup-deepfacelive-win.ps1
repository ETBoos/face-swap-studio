# Pro mode: require NVIDIA build (official _internal/CUDA/bin); stage .dfm; fail with Chinese errors.
# Usage:
#   .\scripts\setup-deepfacelive-win.ps1 -DeepFaceLiveRoot "C:\DeepFaceLive" -DfmPath "D:\models\person.dfm"
#   .\scripts\setup-deepfacelive-win.ps1 -DfmPath "..." -UserdataDir "D:\dfl_ud"
param(
  [string]$DeepFaceLiveRoot = $env:DEEPFACELIVE_ROOT,
  [Parameter(Mandatory = $true)][string]$DfmPath,
  [string]$UserdataDir,
  [string]$DfmVersionHint,
  [switch]$AllowDx12,
  [switch]$AllowUnknownBuild
)

$ErrorActionPreference = "Stop"
$MinDfmBytes = 512KB

function Find-DflRoot {
  param([string]$Hint)
  $candidates = @()
  if ($Hint) { $candidates += $Hint }
  $candidates += @(
    "C:\DeepFaceLive_NVIDIA",
    "$env:USERPROFILE\DeepFaceLive_NVIDIA",
    "C:\DeepFaceLive",
    "$env:USERPROFILE\DeepFaceLive"
  )
  foreach ($c in $candidates) {
    if (-not $c) { continue }
    $bat = Join-Path $c "DeepFaceLive.bat"
    $mainOfficial = Join-Path $c "_internal\DeepFaceLive\main.py"
    $main = Join-Path $c "main.py"
    if ((Test-Path $bat) -or (Test-Path $mainOfficial) -or (Test-Path $main)) {
      return (Resolve-Path $c).Path
    }
  }
  return $null
}

function Get-DflBuildKind {
  param([string]$Root)
  $leaf = Split-Path $Root -Leaf
  $nvidia = @()
  $dx = @()

  if ($leaf -match "nvidia|cuda") { $nvidia += "路径含 NVIDIA/CUDA" }
  if ($leaf -match "dx12|directx|directml") { $dx += "路径含 DX12/DirectX" }

  $cudaBin = Join-Path $Root "_internal\CUDA\bin"
  if (Test-Path $cudaBin) {
    $dlls = @(Get-ChildItem -File $cudaBin -ErrorAction SilentlyContinue |
      Where-Object { $_.Name -match '^(cudnn|cublas|cudart)|nvinfer|nvrtc' } |
      Select-Object -First 4 -ExpandProperty Name)
    if ($dlls.Count -gt 0) { $nvidia += ("_internal/CUDA/bin: " + ($dlls -join ", ")) }
  }

  $ortGpu = Join-Path $Root "_internal\python\Lib\site-packages"
  if (Test-Path $ortGpu) {
    $hit = Get-ChildItem -Recurse -Directory $ortGpu -ErrorAction SilentlyContinue |
      Where-Object { $_.Name -match 'onnxruntime' } |
      Select-Object -First 5
    foreach ($h in $hit) {
      if ($h.FullName -match 'directml') { $dx += "onnxruntime-directml" }
      elseif ($h.FullName -match 'gpu' -or (Test-Path (Join-Path $h.FullName 'onnxruntime_providers_cuda.dll'))) {
        $nvidia += "site-packages CUDA ORT"
      }
    }
  }

  if ($nvidia.Count -gt 0 -and $dx.Count -eq 0) { return @{ Kind = "nvidia"; Evidence = ($nvidia -join "; ") } }
  if ($dx.Count -gt 0 -and $nvidia.Count -eq 0) { return @{ Kind = "dx12"; Evidence = ($dx -join "; ") } }
  if ($nvidia.Count -gt 0) { return @{ Kind = "nvidia"; Evidence = (($nvidia + $dx) -join "; ") } }
  if ($dx.Count -gt 0) { return @{ Kind = "dx12"; Evidence = (($dx + $nvidia) -join "; ") } }
  return @{ Kind = "unknown"; Evidence = "未在根目录或 _internal/CUDA/bin 检测到 NVIDIA/DX12 标记（改名 DeepFaceLive 也应靠 CUDA/bin 识别）" }
}

function Test-DfmFile {
  param([string]$Path, [string]$Hint)
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
    Write-Error "找不到 .dfm 文件：$Path"
  }
  if ([IO.Path]::GetExtension($Path).ToLower() -ne ".dfm") {
    Write-Error "扩展名必须是 .dfm，当前为：$([IO.Path]::GetExtension($Path))"
  }
  $item = Get-Item -LiteralPath $Path
  if ($item.Length -lt $MinDfmBytes) {
    Write-Error (".dfm 过小（{0} 字节）。请用与本机 DeepFaceLive 同代的 DeepFaceLab 重新导出。" -f $item.Length)
  }
  $fs = [IO.File]::OpenRead($Path)
  try {
    $buf = New-Object byte[] 4096
    $n = $fs.Read($buf, 0, 4096)
  } finally { $fs.Close() }
  $ascii = [Text.Encoding]::ASCII.GetString($buf, 0, $n)
  $looks = ($ascii.ToLower().Contains("onnx")) -or ($n -gt 0 -and $buf[0] -eq 8)
  if (-not $looks) {
    Write-Error (".dfm 未通过格式预检（未见 ONNX 指纹）：{0}" -f $item.Name)
  }
  if ($Hint -and $item.Name.ToLower().IndexOf($Hint.ToLower()) -lt 0) {
    Write-Error (".dfm 版本提示不匹配：期望「{0}」，文件「{1}」" -f $Hint, $item.Name)
  }
}

$root = Find-DflRoot -Hint $DeepFaceLiveRoot
if (-not $root) {
  Write-Error "未找到 DeepFaceLive。请安装官方 NVIDIA 便携包（含 _internal\CUDA\bin）并设 DEEPFACELIVE_ROOT。"
}

$build = Get-DflBuildKind -Root $root
Write-Host ("构建检测: {0} ({1})" -f $build.Kind, $build.Evidence)
if ($build.Kind -eq "dx12" -and -not $AllowDx12) {
  Write-Error ("检测到 DX12/DirectML 构建，请改用 NVIDIA。依据：{0}" -f $build.Evidence)
}
if ($build.Kind -eq "unknown" -and -not $AllowUnknownBuild) {
  Write-Error ("无法确认 NVIDIA。{0}。或加 -AllowUnknownBuild" -f $build.Evidence)
}

Test-DfmFile -Path $DfmPath -Hint $DfmVersionHint

$ud = if ($UserdataDir) { $UserdataDir } else { Join-Path $root "userdata" }
$models = Join-Path $ud "dfm_models"
New-Item -ItemType Directory -Force -Path $models | Out-Null
$dest = Join-Path $models (Split-Path $DfmPath -Leaf)
Copy-Item -Force -LiteralPath $DfmPath $dest

Write-Host "DeepFaceLive root: $root"
Write-Host "Build: $($build.Kind)"
Write-Host "Userdata: $ud"
Write-Host "Staged model: $dest"
if ($UserdataDir) {
  Write-Host "注意：自定义 userdata 时壳会用 _internal\python\python.exe + --userdata-dir（官方 bat 写死 %~dp0userdata，不能裸开 bat）。"
} else {
  Write-Host "默认 userdata：可用 .\DeepFaceLive.bat；或由壳启动。"
}
