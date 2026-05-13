Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location -LiteralPath $repoRoot

$runner = Join-Path $repoRoot "tools\run_continuous_hardened_benchmarks.ps1"
if (-not (Test-Path -LiteralPath $runner)) {
    throw "Runner script not found: $runner"
}

$logDir = Join-Path $repoRoot "logs\benchmarks"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$stdoutLog = Join-Path $logDir "continuous_hardened_${stamp}.out.log"
$stderrLog = Join-Path $logDir "continuous_hardened_${stamp}.err.log"

$args = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $runner
)

$proc = Start-Process -FilePath "powershell.exe" `
    -ArgumentList $args `
    -WorkingDirectory $repoRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -PassThru

Write-Output ("Started continuous hardened benchmark runner PID={0}" -f $proc.Id)
Write-Output ("stdout log: {0}" -f $stdoutLog)
Write-Output ("stderr log: {0}" -f $stderrLog)
Write-Output ("status log: {0}" -f (Join-Path $logDir "continuous_hardened_status.log"))
