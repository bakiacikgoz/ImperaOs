param(
  [Parameter(Mandatory = $true)]
  [string]$InstallerPath,
  [string]$ExpectedInstallerSha256 = "",
  [string]$ExpectedProductName = "ImperaOS Operator Panel",
  [string]$OutputDir = "artifacts/windows-installer-smoke",
  [switch]$AllowUnsignedSmoke,
  [switch]$RunInstall,
  [switch]$CleanVm,
  [switch]$RunUninstall,
  [switch]$LaunchAppSmoke,
  [int]$AppLaunchTimeoutSeconds = 10
)

$ErrorActionPreference = "Stop"

function Write-JsonEvidence {
  param(
    [string]$Path,
    [hashtable]$Payload
  )

  $Payload | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $Path -Encoding utf8
}

function Find-InstalledApp {
  param([string]$ProductName)

  $candidates = @(
    @{
      Path = Join-Path $env:LOCALAPPDATA "Programs\$ProductName\$ProductName.exe"
      Kind = "LocalAppData"
    },
    @{
      Path = Join-Path $env:ProgramFiles "$ProductName\$ProductName.exe"
      Kind = "ProgramFiles"
    },
    @{
      Path = Join-Path ${env:ProgramFiles(x86)} "$ProductName\$ProductName.exe"
      Kind = "ProgramFilesX86"
    }
  )
  foreach ($candidate in $candidates) {
    if ($candidate.Path -and (Test-Path -LiteralPath $candidate.Path -PathType Leaf)) {
      return $candidate
    }
  }
  return $null
}

function Get-WebView2Status {
  $clientRoots = @(
    "HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients",
    "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients",
    "HKCU:\SOFTWARE\Microsoft\EdgeUpdate\Clients"
  )
  foreach ($root in $clientRoots) {
    $clients = Get-ChildItem -Path $root -ErrorAction SilentlyContinue
    foreach ($client in $clients) {
      $props = Get-ItemProperty -LiteralPath $client.PSPath -ErrorAction SilentlyContinue
      if ($props -and [string]$props.name -match "WebView2") {
        return "present"
      }
    }
  }
  $runtimePaths = @(
    (Join-Path ${env:ProgramFiles(x86)} "Microsoft\EdgeWebView\Application"),
    (Join-Path $env:ProgramFiles "Microsoft\EdgeWebView\Application"),
    (Join-Path $env:LOCALAPPDATA "Microsoft\EdgeWebView\Application")
  )
  foreach ($runtimePath in $runtimePaths) {
    if ($runtimePath -and (Test-Path -LiteralPath $runtimePath -PathType Container)) {
      return "present"
    }
  }
  return "unknown"
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$GeneratedAtUtc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$ResolvedInstaller = (Resolve-Path -LiteralPath $InstallerPath).Path
$InstallerHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ResolvedInstaller).Hash.ToLowerInvariant()
$ExpectedInstallerHash = $ExpectedInstallerSha256.Trim().ToLowerInvariant()
if (-not [string]::IsNullOrWhiteSpace($ExpectedInstallerHash) -and $ExpectedInstallerHash -notmatch "^[0-9a-f]{64}$") {
  throw "[smoke] ExpectedInstallerSha256 must be a 64-character lowercase/uppercase hex string"
}
$HashContinuityStatus = "not_provided"
if (-not [string]::IsNullOrWhiteSpace($ExpectedInstallerHash)) {
  $HashContinuityStatus = if ($InstallerHash -eq $ExpectedInstallerHash) { "pass" } else { "fail" }
}
$Signature = Get-AuthenticodeSignature -LiteralPath $ResolvedInstaller
$Signed = $Signature.Status -eq "Valid"
$Timestamped = $false
if ($Signature.PSObject.Properties.Name -contains "TimeStamperCertificate") {
  $Timestamped = $null -ne $Signature.TimeStamperCertificate
}
$SmokeSignTool = Get-Command signtool.exe -ErrorAction SilentlyContinue
$SigntoolVerifyStatus = "not_run"
if ($Signed) {
  if ($null -eq $SmokeSignTool) {
    $SigntoolVerifyStatus = "not_found"
  } else {
    & $SmokeSignTool.Source verify /pa /v $ResolvedInstaller | Out-Null
    $SigntoolVerifyStatus = if ($LASTEXITCODE -eq 0) { "pass" } else { "fail" }
  }
}
$RunInstallUsed = [bool]$RunInstall
$AllowUnsignedSmokeUsed = [bool]$AllowUnsignedSmoke
$CleanVmClaimed = [bool]$CleanVm
$WebView2Status = Get-WebView2Status
$GithubHostedRunner = [string]$env:GITHUB_ACTIONS -eq "true"
$RunnerMachine = if ($GithubHostedRunner) { "github-hosted" } else { "local-redacted" }

if (($HashContinuityStatus -eq "fail") -or (-not $Signed -and -not $AllowUnsignedSmoke) -or ($Signed -and -not $AllowUnsignedSmoke -and $SigntoolVerifyStatus -ne "pass")) {
  $blockedReason = "unsigned_installer_requires_AllowUnsignedSmoke"
  if ($HashContinuityStatus -eq "fail") {
    $blockedReason = "installer_hash_mismatch"
  } elseif ($Signed -and $SigntoolVerifyStatus -ne "pass") {
    $blockedReason = "signtool_verify_not_pass"
  }
  $blocked = @{
    schemaVersion = "windows-installer-smoke/v1"
    generated_at_utc = $GeneratedAtUtc
    platform = "windows"
    runner_machine = $RunnerMachine
    github_hosted_runner = $GithubHostedRunner
    installer_sha256 = $InstallerHash
    expected_installer_sha256 = $ExpectedInstallerHash
    hash_continuity_status = $HashContinuityStatus
    signed = $Signed
    timestamped = $Timestamped
    installer_timestamped = $Timestamped
    signature_status = [string]$Signature.Status
    installer_signature_status = [string]$Signature.Status
    signtool_verify_status = $SigntoolVerifyStatus
    clean_vm_claimed = $CleanVmClaimed
    run_install_used = $RunInstallUsed
    allow_unsigned_smoke_used = $AllowUnsignedSmokeUsed
    launch_app_smoke_used = [bool]$LaunchAppSmoke
    os_version = [System.Environment]::OSVersion.VersionString
    powershell_version = $PSVersionTable.PSVersion.ToString()
    webview2_status = $WebView2Status
    app_exe_found = $false
    app_launch_status = "blocked"
    install_root_kind = "unknown"
    install_status = "blocked"
    bundled_runtime_status = "blocked"
    operator_capabilities_status = "blocked"
    doctor_status = "blocked"
    computer_use_live_enabled = $false
    computer_use_enabled = $false
    computer_use_reason_code = "WINDOWS_COMPUTER_USE_NOT_QUALIFIED"
    uninstall_status = "not_run"
    reason = $blockedReason
  }
  Write-JsonEvidence -Path (Join-Path $OutputDir "windows-installer-smoke.json") -Payload $blocked
  throw "[smoke] blocked: $blockedReason"
}

$InstallStatus = "manual"
if ($RunInstall) {
  $process = Start-Process -FilePath $ResolvedInstaller -ArgumentList "/S" -Wait -PassThru
  if ($process.ExitCode -ne 0) {
    throw "[smoke] installer exited with $($process.ExitCode)"
  }
  $InstallStatus = "pass"
}

$AppResult = Find-InstalledApp -ProductName $ExpectedProductName
$AppExe = if ($AppResult) { $AppResult.Path } else { $null }
$InstallRootKind = if ($AppResult) { $AppResult.Kind } else { "unknown" }
if ($RunInstall -and -not $AppExe) {
  $InstallStatus = "fail"
}
$RuntimeStatus = "manual"
$CapabilitiesStatus = "manual"
$DoctorStatus = "manual"
$Capabilities = $null
$Doctor = $null
$ComputerUseEnabled = $false
$UninstallStatus = "not_run"
$AppLaunchStatus = if ($LaunchAppSmoke) { "not_run" } else { "not_requested" }
$AppLaunchExitCode = $null

if ($AppExe) {
  if ($LaunchAppSmoke) {
    try {
      $appProcess = Start-Process -FilePath $AppExe -PassThru
      Start-Sleep -Seconds $AppLaunchTimeoutSeconds
      if ($appProcess.HasExited) {
        $AppLaunchExitCode = $appProcess.ExitCode
        $AppLaunchStatus = if ($appProcess.ExitCode -eq 0) { "pass" } else { "fail" }
      } else {
        $AppLaunchStatus = "pass"
        Stop-Process -Id $appProcess.Id -Force -ErrorAction SilentlyContinue
      }
    } catch {
      $AppLaunchStatus = "fail"
    }
  }

  $resourceRoot = Join-Path (Split-Path -Parent $AppExe) "resources\imperaos-runtime"
  $runtimePython = Join-Path $resourceRoot "python\Scripts\python.exe"
  if (Test-Path -LiteralPath $runtimePython -PathType Leaf) {
    & $runtimePython -m imperaos --version | Set-Content -LiteralPath (Join-Path $OutputDir "imperaos-version.txt")
    if ($LASTEXITCODE -eq 0) {
      $RuntimeStatus = "pass"
    } else {
      $RuntimeStatus = "fail"
    }

    & $runtimePython -m imperaos operator capabilities --json |
      Set-Content -LiteralPath (Join-Path $OutputDir "operator_capabilities.json")
    if ($LASTEXITCODE -eq 0) {
      $CapabilitiesStatus = "pass"
      try {
        $Capabilities = Get-Content -Raw -LiteralPath (Join-Path $OutputDir "operator_capabilities.json") | ConvertFrom-Json
      } catch {
        $CapabilitiesStatus = "fail"
      }
    } else {
      $CapabilitiesStatus = "fail"
    }

    & $runtimePython -m imperaos doctor --profile balanced --json |
      Set-Content -LiteralPath (Join-Path $OutputDir "doctor_balanced.json")
    if ($LASTEXITCODE -eq 0) {
      try {
        $Doctor = Get-Content -Raw -LiteralPath (Join-Path $OutputDir "doctor_balanced.json") | ConvertFrom-Json
        $DoctorStatus = "pass"
      } catch {
        $DoctorStatus = "fail"
      }
    } else {
      $DoctorStatus = "fail"
    }
  } else {
    $RuntimeStatus = "fail"
  }
}

if ($RunUninstall) {
  if ($AppExe) {
    $uninstaller = Join-Path (Split-Path -Parent $AppExe) "uninstall.exe"
    if (Test-Path -LiteralPath $uninstaller -PathType Leaf) {
      $uninstallProcess = Start-Process -FilePath $uninstaller -ArgumentList "/S" -Wait -PassThru
      $UninstallStatus = if ($uninstallProcess.ExitCode -eq 0) { "pass" } else { "fail" }
    } else {
      $UninstallStatus = "not_found"
    }
  } else {
    $UninstallStatus = "not_found"
  }
}

$reasonCode = "WINDOWS_COMPUTER_USE_NOT_QUALIFIED"
if ($Capabilities -and $Capabilities.features.computerUsePilot.reasonCode) {
  $reasonCode = $Capabilities.features.computerUsePilot.reasonCode
}
if ($Capabilities -and $null -ne $Capabilities.features.computerUsePilot.enabled) {
  $ComputerUseEnabled = [bool]$Capabilities.features.computerUsePilot.enabled
}

$report = @{
  schemaVersion = "windows-installer-smoke/v1"
  generated_at_utc = $GeneratedAtUtc
  platform = "windows"
  runner_machine = $RunnerMachine
  github_hosted_runner = $GithubHostedRunner
  installer_sha256 = $InstallerHash
  expected_installer_sha256 = $ExpectedInstallerHash
  hash_continuity_status = $HashContinuityStatus
  signed = $Signed
  timestamped = $Timestamped
  installer_timestamped = $Timestamped
  signature_status = [string]$Signature.Status
  installer_signature_status = [string]$Signature.Status
  signtool_verify_status = $SigntoolVerifyStatus
  clean_vm_claimed = $CleanVmClaimed
  run_install_used = $RunInstallUsed
  allow_unsigned_smoke_used = $AllowUnsignedSmokeUsed
  launch_app_smoke_used = [bool]$LaunchAppSmoke
  os_version = [System.Environment]::OSVersion.VersionString
  powershell_version = $PSVersionTable.PSVersion.ToString()
  webview2_status = $WebView2Status
  app_exe_found = $null -ne $AppExe
  app_launch_status = $AppLaunchStatus
  app_launch_exit_code = $AppLaunchExitCode
  install_root_kind = $InstallRootKind
  install_status = $InstallStatus
  bundled_runtime_status = $RuntimeStatus
  operator_capabilities_status = $CapabilitiesStatus
  doctor_status = $DoctorStatus
  computer_use_live_enabled = $ComputerUseEnabled
  computer_use_enabled = $ComputerUseEnabled
  computer_use_reason_code = $reasonCode
  uninstall_status = $UninstallStatus
}
Write-JsonEvidence -Path (Join-Path $OutputDir "windows-installer-smoke.json") -Payload $report

Write-Output "[smoke] report=$(Join-Path $OutputDir "windows-installer-smoke.json")"
