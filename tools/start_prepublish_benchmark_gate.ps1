param(
    [switch]$Parallel,
    [int]$MaxParallel = 3,
    [int]$LaneTimeoutMinutes = 240,
    [int]$IdleTimeoutMinutes = 20,
    [string]$ProjectSuffix = "",
    [switch]$Resume
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location -LiteralPath $repoRoot

$runner = Join-Path $repoRoot "tools\prepublish_benchmark_gate.ps1"
if (-not (Test-Path -LiteralPath $runner)) {
    throw "Prepublish benchmark gate not found: $runner"
}

$logDir = Join-Path $repoRoot "logs\benchmarks"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$stdoutLog = Join-Path $logDir "prepublish_gate_launcher_${stamp}.out.log"
$stderrLog = Join-Path $logDir "prepublish_gate_launcher_${stamp}.err.log"

$argList = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $runner,
    "-MaxParallel", $MaxParallel,
    "-LaneTimeoutMinutes", $LaneTimeoutMinutes,
    "-IdleTimeoutMinutes", $IdleTimeoutMinutes
)
if ($Parallel) {
    $argList += "-Parallel"
}
if (-not [string]::IsNullOrWhiteSpace($ProjectSuffix)) {
    $argList += @("-ProjectSuffix", $ProjectSuffix)
}
if ($Resume) {
    $argList += "-Resume"
}

$proc = Start-Process -FilePath "powershell.exe" `
    -ArgumentList $argList `
    -WorkingDirectory $repoRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -PassThru

Write-Output ("Started prepublish benchmark gate PID={0}" -f $proc.Id)
Write-Output ("parallel: {0}" -f $Parallel.IsPresent)
Write-Output ("max_parallel: {0}" -f $MaxParallel)
Write-Output ("lane_timeout_minutes: {0}" -f $LaneTimeoutMinutes)
Write-Output ("idle_timeout_minutes: {0}" -f $IdleTimeoutMinutes)
Write-Output ("project_suffix: {0}" -f $ProjectSuffix)
Write-Output ("resume: {0}" -f $Resume.IsPresent)
Write-Output ("stdout log: {0}" -f $stdoutLog)
Write-Output ("stderr log: {0}" -f $stderrLog)
