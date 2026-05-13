Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location -LiteralPath $repoRoot

$runSweep = Join-Path $repoRoot "tools\run_full_leaderboard_sweeps.ps1"
$reportPy = Join-Path $repoRoot "tools\report_full_sweep_leaderboard.py"
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $runSweep)) { throw "Missing: $runSweep" }
if (-not (Test-Path -LiteralPath $reportPy)) { throw "Missing: $reportPy" }
if (-not (Test-Path -LiteralPath $python)) { throw "Missing: $python" }

$intervalMinutes = 30
$override = $env:MAPU_CONTINUOUS_BENCH_INTERVAL_MINUTES
if ($override) {
    $parsed = 0
    if ([int]::TryParse($override, [ref]$parsed) -and $parsed -ge 1) {
        $intervalMinutes = $parsed
    }
}

$logDir = Join-Path $repoRoot "logs\benchmarks"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$statusLog = Join-Path $logDir "continuous_hardened_status.log"

while ($true) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $loopOut = Join-Path $logDir "continuous_${stamp}.out.log"
    $loopErr = Join-Path $logDir "continuous_${stamp}.err.log"
    $leaderboard = Join-Path $logDir "continuous_${stamp}.leaderboard.txt"

    Add-Content -LiteralPath $statusLog -Value ("[{0}] cycle_start stamp={1}" -f (Get-Date -Format "s"), $stamp)

    try {
        powershell -NoProfile -ExecutionPolicy Bypass -File $runSweep 1> $loopOut 2> $loopErr
        if ($LASTEXITCODE -ne 0) { throw "sweep failed: $LASTEXITCODE" }

        & $python $reportPy 1> $leaderboard
        if ($LASTEXITCODE -ne 0) { throw "leaderboard report failed: $LASTEXITCODE" }

        Add-Content -LiteralPath $statusLog -Value ("[{0}] cycle_pass stamp={1} out={2} err={3} leaderboard={4}" -f (Get-Date -Format "s"), $stamp, $loopOut, $loopErr, $leaderboard)
    }
    catch {
        Add-Content -LiteralPath $statusLog -Value ("[{0}] cycle_fail stamp={1} error={2}" -f (Get-Date -Format "s"), $stamp, $_.Exception.Message)
    }

    Start-Sleep -Seconds ($intervalMinutes * 60)
}
