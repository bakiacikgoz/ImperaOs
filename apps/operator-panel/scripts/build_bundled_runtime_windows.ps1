param(
  [ValidateSet("x64")]
  [string]$Arch = "x64",
  [string]$PythonBin = "py -3.11",
  [string]$WheelPath = ""
)

$ErrorActionPreference = "Stop"

function Resolve-PythonCommand {
  param([string]$Command)

  $trimmed = $Command.Trim()
  if ($trimmed.Length -eq 0) {
    throw "[runtime] PythonBin must not be empty"
  }

  if (Test-Path -LiteralPath $trimmed) {
    return @{ Exe = (Resolve-Path -LiteralPath $trimmed).Path; Args = @() }
  }

  $parts = $trimmed -split "\s+"
  return @{ Exe = $parts[0]; Args = @($parts | Select-Object -Skip 1) }
}

function Invoke-Checked {
  param(
    [string]$FilePath,
    [string[]]$Arguments
  )

  & $FilePath @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "[runtime] command failed ($LASTEXITCODE): $FilePath $($Arguments -join ' ')"
  }
}

function Get-FileSha256 {
  param([string]$Path)

  return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $ScriptDir "..\..\..")).Path
$AppDir = Join-Path $RepoRoot "apps\operator-panel"
$RuntimeDir = Join-Path $AppDir "src-tauri\resources\imperaos-runtime"
$RuntimeParent = Split-Path -Parent $RuntimeDir
$RuntimePythonDir = Join-Path $RuntimeDir "python"
$RuntimePython = Join-Path $RuntimePythonDir "Scripts\python.exe"
$DistDir = Join-Path $RepoRoot "dist"

if ($Arch -ne "x64") {
  throw "[runtime] unsupported arch: $Arch"
}

$RuntimeParentResolved = (Resolve-Path -LiteralPath $RuntimeParent).Path
if (-not $RuntimeDir.StartsWith($RuntimeParentResolved, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw "[runtime] refusing to clean unexpected runtime path: $RuntimeDir"
}

New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

if ([string]::IsNullOrWhiteSpace($WheelPath)) {
  Write-Host "[runtime] building ImperaOS wheel"
  Push-Location $RepoRoot
  try {
    Invoke-Checked -FilePath "uv" -Arguments @("build", "--wheel", "--out-dir", $DistDir)
  } finally {
    Pop-Location
  }
  $latestWheel = Get-ChildItem -Path $DistDir -Filter "imperaos-*.whl" |
    Sort-Object LastWriteTimeUtc -Descending |
    Select-Object -First 1
  if ($null -eq $latestWheel) {
    throw "[runtime] no ImperaOS wheel found in $DistDir"
  }
  $WheelPath = $latestWheel.FullName
}

if (-not (Test-Path -LiteralPath $WheelPath -PathType Leaf)) {
  throw "[runtime] wheel not found: $WheelPath"
}

$python = Resolve-PythonCommand -Command $PythonBin

Write-Host "[runtime] target platform=windows arch=$Arch"
if (Test-Path -LiteralPath $RuntimeDir) {
  Remove-Item -LiteralPath $RuntimeDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null

Invoke-Checked -FilePath $python.Exe -Arguments @($python.Args + @("-m", "venv", $RuntimePythonDir))

if (-not (Test-Path -LiteralPath $RuntimePython -PathType Leaf)) {
  throw "[runtime] invalid runtime: expected $RuntimePython"
}

Invoke-Checked -FilePath $RuntimePython -Arguments @("-m", "pip", "install", "--upgrade", "pip", "wheel")
Invoke-Checked -FilePath $RuntimePython -Arguments @("-m", "pip", "install", $WheelPath)

$version = (& $RuntimePython -m imperaos --version)
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($version)) {
  throw "[runtime] runtime validation failed: $RuntimePython -m imperaos --version"
}

$UvLockPath = Join-Path $RepoRoot "uv.lock"
$UvLockHash = if (Test-Path -LiteralPath $UvLockPath -PathType Leaf) { Get-FileSha256 -Path $UvLockPath } else { "missing" }
$GitSha = "unknown"
try {
  $gitOutput = & git -C $RepoRoot rev-parse HEAD 2>$null
  if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($gitOutput)) {
    $GitSha = $gitOutput.Trim()
  }
} catch {
  $GitSha = "unknown"
}

$manifest = @(
  "platform=windows",
  "arch=x86_64",
  "python=python/Scripts/python.exe",
  "imperaos_version=$($version.Trim())",
  "created_at_utc=$((Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ"))",
  "source_wheel=$WheelPath",
  "source_wheel_sha256=$(Get-FileSha256 -Path $WheelPath)",
  "python_exe_sha256=$(Get-FileSha256 -Path $RuntimePython)",
  "uv_lock_sha256=$UvLockHash",
  "git_sha=$GitSha"
)
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllLines((Join-Path $RuntimeDir "RUNTIME_MANIFEST.txt"), $manifest, $Utf8NoBom)

@"
Generated Windows runtime bundle for ImperaOS Operator Panel.

Release gate:
1) python/Scripts/python.exe exists
2) python/Scripts/python.exe -m imperaos --version passes
3) RUNTIME_MANIFEST.txt records platform, arch, Python entrypoint, source wheel, hashes, and git evidence

Do not ship placeholder-only runtime contents.
"@ | Set-Content -LiteralPath (Join-Path $RuntimeDir "README.txt") -Encoding utf8

Write-Host "[runtime] bundled runtime ready: $RuntimeDir"
