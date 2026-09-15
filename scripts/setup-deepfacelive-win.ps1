# Pro mode: require NVIDIA build when possible; stage .dfm; fail with readable Chinese errors.
# Usage:
#   .\scripts\setup-deepfacelive-win.ps1 -DeepFaceLiveRoot "C:\DeepFaceLive_NVIDIA" -DfmPath "D:\models\person.dfm"
#   .\scripts\setup-deepfacelive-win.ps1 -DfmPath "...\person.dfm" -AllowUnknownBuild
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
    if ((Test-Path (Join-Path $c "DeepFaceLive.bat")) -or (Test-Path (Join-Path $c "main.py"))) {
      return (Resolve-Path $c).Path
    }
  }
  return $null
}

function Get-DflBuildKind {
  param([string]$Root)
  $leaf = Split-Path $Root -Leaf
  $files = @()
  try { $files = Get-ChildItem -File $Root -ErrorAction SilentlyContinue | Select-Object -First 80 -ExpandProperty Name } catch {}
  $blob = ($leaf + " " + ($files -join " ")).ToLowerInvariant()

  $nvidia = @()
  if ($blob -match "nvidia|cuda") { $nvidia += "路径/文件名含 NVIDIA/CUDA" }
  $cudaDlls = @($files | Where-Object { $_ -match '^(cudnn|cublas|cudart)' -or $_ -match 'nvinfer' })
  if ($cudaDlls.Count -gt 0) { $nvidia += ("CUDA 文件: " + ($cudaDlls[0..([Math]::Min(3, $cudaDlls.Count-1))] -join ", ")) }

  $dx = @()
  if ($blob -match "dx12|directx") { $dx += "路径含 DX12/DirectX" }
  $dxDlls = @($files | Where-Object { $_ -match 'd3d12|_dx12\.dll' })
  if ($dxDlls.Count -gt 0) { $dx += ("DX12 文件: " + ($dxDlls[0..([Math]::Min(3, $dxDlls.Count-1))] -join ", ")) }

  if ($nvidia.Count -gt 0 -and $dx.Count -eq 0) { return @{ Kind = "nvidia"; Evidence = ($nvidia -join "; ") } }
  if ($dx.Count -gt 0 -and $nvidia.Count -eq 0) { return @{ Kind = "dx12"; Evidence = ($dx -join "; ") } }
  if ($cudaDlls.Count -gt 0) { return @{ Kind = "nvidia"; Evidence = ($nvidia + $dx -join "; ") } }
  if ($dx.Count -gt 0) { return @{ Kind = "dx12"; Evidence = ($dx + $nvidia -join "; ") } }
  return @{ Kind = "unknown"; Evidence = "未检测到明确的 NVIDIA/CUDA 或 DX12 标记" }
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
    Write-Error (".dfm 过小（{0} 字节），更像损坏或占位文件；真实专模通常 ≥ 512KB。请用与本机 DeepFaceLive 同代的 DeepFaceLab 重新导出。" -f $item.Length)
  }
  $fs = [IO.File]::OpenRead($Path)
  try {
    $buf = New-Object byte[] 4096
    $n = $fs.Read($buf, 0, 4096)
  } finally { $fs.Close() }
  $ascii = [Text.Encoding]::ASCII.GetString($buf, 0, $n)
  $looks = ($ascii.ToLower().Contains("onnx")) -or ($n -gt 0 -and $buf[0] -eq 8)
  if (-not $looks) {
    Write-Error (".dfm 未通过格式预检（未见 ONNX/模型指纹）：{0}。常见原因：文件损坏、不是 DFL 专模、或导出版本与本机 DeepFaceLive 不匹配。请用同代 DeepFaceLab 重新导出。" -f $item.Name)
  }
  if ($Hint) {
    $name = $item.Name
    if ($name.ToLower().IndexOf($Hint.ToLower()) -lt 0) {
      $sidecar = "$Path.version"
      $okSide = $false
      if (Test-Path $sidecar) {
        $okSide = ((Get-Content -Raw $sidecar).Trim() -eq $Hint)
      }
      if (-not $okSide) {
        Write-Error (".dfm 版本提示不匹配：期望「{0}」，文件名为「{1}」。请确认导出 DFL 与本机 DeepFaceLive NVIDIA 包为同一代。" -f $Hint, $name)
      }
    }
  }
}

$root = Find-DflRoot -Hint $DeepFaceLiveRoot
if (-not $root) {
  Write-Error "未找到 DeepFaceLive。请安装 **NVIDIA 构建** 并传入 -DeepFaceLiveRoot，或设置 DEEPFACELIVE_ROOT。"
}

$build = Get-DflBuildKind -Root $root
Write-Host ("构建检测: {0} ({1})" -f $build.Kind, $build.Evidence)
if ($build.Kind -eq "dx12" -and -not $AllowDx12) {
  Write-Error ("检测到 DX12 构建，顶级实时请改用 NVIDIA 构建。依据：{0}。目录：{1}" -f $build.Evidence, $root)
}
if ($build.Kind -eq "unknown" -and -not $AllowUnknownBuild) {
  Write-Error ("无法确认 NVIDIA 构建。{0}。请指向含 cudnn/cublas 的 NVIDIA 包，或加 -AllowUnknownBuild（不推荐）。目录：{1}" -f $build.Evidence, $root)
}

Test-DfmFile -Path $DfmPath -Hint $DfmVersionHint

$ud = if ($UserdataDir) { $UserdataDir } else { Join-Path $root "userdata" }
$models = Join-Path $ud "dfm_models"
New-Item -ItemType Directory -Force -Path $models | Out-Null
$dest = Join-Path $models (Split-Path $DfmPath -Leaf)
Copy-Item -Force -LiteralPath $DfmPath $dest

Write-Host "DeepFaceLive root: $root"
Write-Host "Build: $($build.Kind)"
Write-Host "Staged model: $dest"
Write-Host "启动后在 Face swapper 中选择该模型：cd `"$root`"; .\DeepFaceLive.bat"
