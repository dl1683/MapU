Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location -LiteralPath $repoRoot

$runner = Join-Path $repoRoot "tools\run_full_leaderboard_sweeps.ps1"
if (-not (Test-Path -LiteralPath $runner)) {
    throw "Runner script not found: $runner"
}

$logDir = Join-Path $repoRoot "logs\benchmarks"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$stdoutLog = Join-Path $logDir "full_sweeps_${stamp}.out.log"
$stderrLog = Join-Path $logDir "full_sweeps_${stamp}.err.log"

$argList = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $runner
)

$proc = Start-Process -FilePath "powershell.exe" `
    -ArgumentList $argList `
    -WorkingDirectory $repoRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -PassThru

Write-Output ("Started full benchmark sweep runner PID={0}" -f $proc.Id)
Write-Output ("stdout log: {0}" -f $stdoutLog)
Write-Output ("stderr log: {0}" -f $stderrLog)
