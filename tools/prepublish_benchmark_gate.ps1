param(
    [switch]$Parallel,
    [int]$MaxParallel = 2
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location -LiteralPath $repoRoot

$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$runSweep = Join-Path $repoRoot "tools\run_full_leaderboard_sweeps.ps1"
$runParallelSweep = Join-Path $repoRoot "tools\run_full_leaderboard_sweeps_parallel.ps1"
$report = Join-Path $repoRoot "tools\report_full_sweep_leaderboard.py"
$statusDoc = Join-Path $repoRoot "GLOBAL_MEMORY_BENCHMARK_STATUS.md"

if (-not (Test-Path -LiteralPath $python)) { throw "Missing python: $python" }
if (-not (Test-Path -LiteralPath $runSweep)) { throw "Missing sweep runner: $runSweep" }
if ($Parallel -and -not (Test-Path -LiteralPath $runParallelSweep)) { throw "Missing parallel sweep runner: $runParallelSweep" }
if (-not (Test-Path -LiteralPath $report)) { throw "Missing report script: $report" }

$logDir = Join-Path $repoRoot "logs\benchmarks"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$env:MAPU_BENCH_PROJECT_SUFFIX = "prepublish_$stamp"
Remove-Item Env:\MAPU_BENCH_SKIP_INGEST -ErrorAction SilentlyContinue
$gateDir = Join-Path $logDir "prepublish_gate_$stamp"
New-Item -ItemType Directory -Force -Path $gateDir | Out-Null

$sweepOut = Join-Path $gateDir "sweep.out.log"
$sweepErr = Join-Path $gateDir "sweep.err.log"
$leaderboardOut = Join-Path $gateDir "leaderboard.txt"
$codeIdentity = Join-Path $gateDir "code_identity.txt"
$gateMeta = Join-Path $gateDir "gate_meta.json"

$gitSha = (& git rev-parse HEAD 2>$null)
if ($LASTEXITCODE -ne 0) { $gitSha = "unknown" }
$dirty = (& git status --porcelain 2>$null)
if ($LASTEXITCODE -ne 0) { $dirty = "" }
$dirtyFlag = if ([string]::IsNullOrWhiteSpace($dirty)) { "clean" } else { "dirty" }
"sha=$gitSha`nworktree=$dirtyFlag`ntimestamp=$stamp`nparallel=$($Parallel.IsPresent)`nmax_parallel=$MaxParallel" | Set-Content -LiteralPath $codeIdentity -Encoding UTF8

try {
    if ($Parallel) {
        powershell -NoProfile -ExecutionPolicy Bypass -File $runParallelSweep -MaxParallel $MaxParallel 1> $sweepOut 2> $sweepErr
    }
    else {
        powershell -NoProfile -ExecutionPolicy Bypass -File $runSweep 1> $sweepOut 2> $sweepErr
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Sweep failed with exit code $LASTEXITCODE"
    }

    & $python $report 1> $leaderboardOut
    if ($LASTEXITCODE -ne 0) {
        throw "Leaderboard report failed with exit code $LASTEXITCODE"
    }

    $meta = [ordered]@{
        timestamp = $stamp
        git_sha = $gitSha
        worktree = $dirtyFlag
        sweep_out_log = $sweepOut
        sweep_err_log = $sweepErr
        leaderboard_report = $leaderboardOut
        status_doc = $statusDoc
        parallel = $Parallel.IsPresent
        max_parallel = $MaxParallel
        gate_pass = $true
    }
    ($meta | ConvertTo-Json -Depth 4) | Set-Content -LiteralPath $gateMeta -Encoding UTF8

    Write-Output "PREPUBLISH BENCHMARK GATE: PASS"
    Write-Output "gate dir: $gateDir"
    Write-Output "code identity: $codeIdentity"
    Write-Output "leaderboard: $leaderboardOut"
}
catch {
    $meta = [ordered]@{
        timestamp = $stamp
        git_sha = $gitSha
        worktree = $dirtyFlag
        sweep_out_log = $sweepOut
        sweep_err_log = $sweepErr
        leaderboard_report = $leaderboardOut
        status_doc = $statusDoc
        parallel = $Parallel.IsPresent
        max_parallel = $MaxParallel
        gate_pass = $false
        error = $_.Exception.Message
    }
    ($meta | ConvertTo-Json -Depth 4) | Set-Content -LiteralPath $gateMeta -Encoding UTF8
    Write-Error "PREPUBLISH BENCHMARK GATE: FAIL - $($_.Exception.Message)"
    exit 1
}
