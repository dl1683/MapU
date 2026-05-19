param(
    [switch]$Parallel,
    [switch]$SkipServicePreflight,
    [switch]$PreflightOnly,
    [int]$MaxParallel = 2,
    [int]$LaneTimeoutMinutes = 240,
    [int]$IdleTimeoutMinutes = 20,
    [string]$ProjectSuffix = "",
    [switch]$Resume
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location -LiteralPath $repoRoot

$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$runSweep = Join-Path $repoRoot "tools\run_full_leaderboard_sweeps.ps1"
$runParallelSweep = Join-Path $repoRoot "tools\run_full_leaderboard_sweeps_parallel.ps1"
$report = Join-Path $repoRoot "tools\report_full_sweep_leaderboard.py"
$verifyBenchmarkEvidence = Join-Path $repoRoot "tools\verify_prepublish_benchmark_evidence.py"
$statusDoc = Join-Path $repoRoot "GLOBAL_MEMORY_BENCHMARK_STATUS.md"
$modelBaseUrl = "http://localhost:11434/v1"
$benchmarkMem0HostArg = "http://localhost:8000"

if (-not (Test-Path -LiteralPath $python)) { throw "Missing python: $python" }
if (-not (Test-Path -LiteralPath $runSweep)) { throw "Missing sweep runner: $runSweep" }
if ($Parallel -and -not (Test-Path -LiteralPath $runParallelSweep)) { throw "Missing parallel sweep runner: $runParallelSweep" }
if (-not (Test-Path -LiteralPath $report)) { throw "Missing report script: $report" }
if (-not (Test-Path -LiteralPath $verifyBenchmarkEvidence)) { throw "Missing benchmark evidence verifier: $verifyBenchmarkEvidence" }

function Write-TextUtf8NoBom {
    param(
        [string]$Text,
        [string]$Path
    )

    $absolutePath = [System.IO.Path]::GetFullPath($Path)
    $parent = [System.IO.Path]::GetDirectoryName($absolutePath)
    if (-not [string]::IsNullOrWhiteSpace($parent)) {
        [System.IO.Directory]::CreateDirectory($parent) | Out-Null
    }
    $encoding = New-Object System.Text.UTF8Encoding -ArgumentList $false
    [System.IO.File]::WriteAllText($absolutePath, ($Text + [Environment]::NewLine), $encoding)
}

function Write-JsonUtf8NoBom {
    param(
        [object]$Data,
        [string]$Path,
        [int]$Depth = 5
    )

    $json = $Data | ConvertTo-Json -Depth $Depth
    Write-TextUtf8NoBom -Text $json -Path $Path
}

function New-GateMetadata {
    param(
        [string]$Status,
        [bool]$GatePass,
        [bool]$PublicPerformanceEvidence,
        [bool]$BenchmarkEvidenceVerified,
        [object]$BenchmarkEvidenceVerifiedAt = $null,
        [string]$ErrorMessage = ""
    )

    $meta = [ordered]@{
        timestamp = $stamp
        git_sha = $gitSha
        worktree = $dirtyFlag
        sweep_out_log = $sweepOut
        sweep_err_log = $sweepErr
        lane_artifact_dir = $laneArtifactDir
        leaderboard_report = $leaderboardOut
        code_identity = $codeIdentity
        benchmark_evidence_verifier = $benchmarkVerifierOut
        status_doc = $statusDoc
        model_base_url = $modelBaseUrl
        benchmark_mem0_host_arg = $benchmarkMem0HostArg
        skip_service_preflight = $SkipServicePreflight.IsPresent
        preflight_only = $PreflightOnly.IsPresent
        preflight_status = $preflightStatus
        preflight_checks = $preflightChecks
        parallel = $Parallel.IsPresent
        max_parallel = $MaxParallel
        lane_timeout_minutes = $LaneTimeoutMinutes
        idle_timeout_minutes = $IdleTimeoutMinutes
        project_suffix = $env:MAPU_BENCH_PROJECT_SUFFIX
        resume = $Resume.IsPresent
        status = $Status
        gate_pass = $GatePass
        public_performance_evidence = $PublicPerformanceEvidence
        benchmark_evidence_verified = $BenchmarkEvidenceVerified
        benchmark_evidence_verified_at = $BenchmarkEvidenceVerifiedAt
    }
    if (-not [string]::IsNullOrWhiteSpace($ErrorMessage)) {
        $meta["error"] = $ErrorMessage
    }
    return $meta
}

$logDir = Join-Path $repoRoot "logs\benchmarks"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$providedProjectSuffix = $ProjectSuffix.Trim()
if (-not [string]::IsNullOrWhiteSpace($providedProjectSuffix)) {
    if ($providedProjectSuffix -notmatch "^prepublish_\d{8}_\d{6}$") {
        throw "ProjectSuffix must be blank or match prepublish_yyyyMMdd_HHmmss"
    }
    $stamp = $providedProjectSuffix.Substring("prepublish_".Length)
    $env:MAPU_BENCH_PROJECT_SUFFIX = $providedProjectSuffix
}
else {
    $env:MAPU_BENCH_PROJECT_SUFFIX = "prepublish_$stamp"
}
Remove-Item Env:\MAPU_BENCH_SKIP_INGEST -ErrorAction SilentlyContinue
$gateDir = Join-Path $logDir "prepublish_gate_$stamp"
New-Item -ItemType Directory -Force -Path $gateDir | Out-Null

$sweepOut = Join-Path $gateDir "sweep.out.log"
$sweepErr = Join-Path $gateDir "sweep.err.log"
$leaderboardOut = Join-Path $gateDir "leaderboard.txt"
$codeIdentity = Join-Path $gateDir "code_identity.txt"
$gateMeta = Join-Path $gateDir "gate_meta.json"
$benchmarkVerifierOut = Join-Path $gateDir "benchmark_evidence_verifier.json"
$laneArtifactDir = if ($Parallel) {
    Join-Path $logDir ("parallel_{0}" -f $env:MAPU_BENCH_PROJECT_SUFFIX)
}
else {
    Join-Path $logDir ("sweep_{0}" -f $env:MAPU_BENCH_PROJECT_SUFFIX)
}

$gitSha = (& git rev-parse HEAD 2>$null)
if ($LASTEXITCODE -ne 0) { $gitSha = "unknown" }
$dirty = (& git status --porcelain 2>$null)
if ($LASTEXITCODE -ne 0) { $dirty = "" }
$dirtyFlag = if ([string]::IsNullOrWhiteSpace($dirty)) { "clean" } else { "dirty" }
if ($Resume -and [string]::IsNullOrWhiteSpace($providedProjectSuffix)) {
    throw "Resume requires -ProjectSuffix prepublish_yyyyMMdd_HHmmss so checkpoint reuse is explicit"
}
if ($Resume -and -not (Test-Path -LiteralPath $codeIdentity)) {
    throw "Resume requested, but existing code identity was not found for $($env:MAPU_BENCH_PROJECT_SUFFIX): $codeIdentity"
}
if (-not [string]::IsNullOrWhiteSpace($providedProjectSuffix) -and (Test-Path -LiteralPath $codeIdentity)) {
    $existingIdentity = @{}
    Get-Content -LiteralPath $codeIdentity | ForEach-Object {
        if ($_ -match "^([^=]+)=(.*)$") {
            $existingIdentity[$Matches[1]] = $Matches[2]
        }
    }
    if ($existingIdentity.ContainsKey("sha") -and $existingIdentity["sha"] -ne $gitSha) {
        throw "Refusing to reuse $($env:MAPU_BENCH_PROJECT_SUFFIX): existing code sha $($existingIdentity["sha"]) does not match current sha $gitSha"
    }
    if ($existingIdentity.ContainsKey("worktree") -and $existingIdentity["worktree"] -ne $dirtyFlag) {
        throw "Refusing to reuse $($env:MAPU_BENCH_PROJECT_SUFFIX): existing worktree $($existingIdentity["worktree"]) does not match current worktree $dirtyFlag"
    }
}
Write-TextUtf8NoBom -Path $codeIdentity -Text "sha=$gitSha`nworktree=$dirtyFlag`ntimestamp=$stamp`nparallel=$($Parallel.IsPresent)`nskip_service_preflight=$($SkipServicePreflight.IsPresent)`npreflight_only=$($PreflightOnly.IsPresent)`nmodel_base_url=$modelBaseUrl`nbenchmark_mem0_host_arg=$benchmarkMem0HostArg`nmax_parallel=$MaxParallel`nlane_timeout_minutes=$LaneTimeoutMinutes`nidle_timeout_minutes=$IdleTimeoutMinutes`nproject_suffix=$($env:MAPU_BENCH_PROJECT_SUFFIX)`nresume=$($Resume.IsPresent)"
$preflightStatus = if ($SkipServicePreflight) { "skipped" } else { "not_run" }
$preflightChecks = [ordered]@{}

function Test-HttpEndpoint {
    param(
        [string]$Name,
        [string]$Uri
    )

    try {
        $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 8
    }
    catch {
        $script:preflightChecks[$Name] = [ordered]@{
            kind = "http"
            uri = $Uri
            status = "fail"
            error = $_.Exception.Message
        }
        throw "$Name is not reachable at ${Uri}: $($_.Exception.Message)"
    }
    if ([int]$response.StatusCode -ge 500) {
        $script:preflightChecks[$Name] = [ordered]@{
            kind = "http"
            uri = $Uri
            status = "fail"
            http_status = [int]$response.StatusCode
            error = "HTTP $($response.StatusCode)"
        }
        throw "$Name returned HTTP $($response.StatusCode) from $Uri"
    }
    $script:preflightChecks[$Name] = [ordered]@{
        kind = "http"
        uri = $Uri
        status = "ok"
        http_status = [int]$response.StatusCode
    }
    Write-Output ("PREPUBLISH PREFLIGHT: PASS {0} http {1} status={2}" -f $Name, $Uri, $response.StatusCode)
}

function Test-MapUDatabase {
    $probe = @'
import asyncio
from sqlalchemy import text
from mapu.config import Settings
from mapu.db.engine import build_engine

async def main() -> None:
    settings = Settings()
    engine, _ = build_engine(settings.database)
    try:
        async with engine.connect() as conn:
            await conn.execute(text('select 1'))
    finally:
        await engine.dispose()

asyncio.run(main())
'@

    $output = & $python -c $probe 2>&1
    if ($LASTEXITCODE -ne 0) {
        $message = ($output | Out-String).Trim()
        $script:preflightChecks["mapu database"] = [ordered]@{
            kind = "database"
            status = "fail"
            error = $message
        }
        throw "MapU database is not reachable via MAPU_DB_URL: $message"
    }
    $script:preflightChecks["mapu database"] = [ordered]@{
        kind = "database"
        status = "ok"
    }
    Write-Output "PREPUBLISH PREFLIGHT: PASS mapu database"
}

try {
    if (-not $SkipServicePreflight) {
        Test-HttpEndpoint -Name "model endpoint" -Uri "$modelBaseUrl/models"
        Test-MapUDatabase
        $preflightStatus = "ok"
    }
    else {
        Write-Output "PREPUBLISH PREFLIGHT: SKIP service checks (-SkipServicePreflight set)"
    }

    if ($PreflightOnly) {
        $meta = New-GateMetadata `
            -Status "preflight_only" `
            -GatePass $false `
            -PublicPerformanceEvidence $false `
            -BenchmarkEvidenceVerified $false `
            -ErrorMessage "preflight-only run; benchmark lanes were not executed"
        Write-JsonUtf8NoBom -Data $meta -Path $gateMeta -Depth 5
        Write-Output "PREPUBLISH BENCHMARK GATE: PREFLIGHT ONLY"
        Write-Output "gate dir: $gateDir"
        Write-Output "gate metadata: $gateMeta"
        exit 0
    }

    $meta = New-GateMetadata `
        -Status "running" `
        -GatePass $false `
        -PublicPerformanceEvidence $false `
        -BenchmarkEvidenceVerified $false `
        -ErrorMessage "benchmark lanes are running; this is not public performance evidence"
    Write-JsonUtf8NoBom -Data $meta -Path $gateMeta -Depth 5

    if ($Parallel) {
        $sweepArgs = @(
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", $runParallelSweep,
            "-MaxParallel", $MaxParallel,
            "-LaneTimeoutMinutes", $LaneTimeoutMinutes,
            "-IdleTimeoutMinutes", $IdleTimeoutMinutes,
            "-BenchmarkMem0HostArg", $benchmarkMem0HostArg
        )
    }
    else {
        $sweepArgs = @(
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", $runSweep,
            "-BenchmarkMem0HostArg", $benchmarkMem0HostArg
        )
    }
    if ($Resume) {
        $sweepArgs += "-Resume"
    }
    powershell @sweepArgs 1> $sweepOut 2> $sweepErr
    if ($LASTEXITCODE -ne 0) {
        throw "Sweep failed with exit code $LASTEXITCODE"
    }

    & $python $report 1> $leaderboardOut
    if ($LASTEXITCODE -ne 0) {
        throw "Leaderboard report failed with exit code $LASTEXITCODE"
    }

    $meta = New-GateMetadata `
        -Status "sweep_complete_unverified" `
        -GatePass $true `
        -PublicPerformanceEvidence $false `
        -BenchmarkEvidenceVerified $false
    Write-JsonUtf8NoBom -Data $meta -Path $gateMeta -Depth 4

    & $python $verifyBenchmarkEvidence $gateMeta 1> $benchmarkVerifierOut
    if ($LASTEXITCODE -ne 0) {
        throw "Benchmark evidence verifier failed with exit code $LASTEXITCODE"
    }
    $meta["public_performance_evidence"] = $true
    $meta["benchmark_evidence_verified"] = $true
    $meta["benchmark_evidence_verified_at"] = (Get-Date -Format "o")
    $meta["status"] = "passed"
    Write-JsonUtf8NoBom -Data $meta -Path $gateMeta -Depth 4

    & $python $verifyBenchmarkEvidence $gateMeta --require-public-evidence-labels 1> $benchmarkVerifierOut
    if ($LASTEXITCODE -ne 0) {
        throw "Benchmark evidence label verifier failed with exit code $LASTEXITCODE"
    }

    Write-Output "PREPUBLISH BENCHMARK GATE: PASS"
    Write-Output "gate dir: $gateDir"
    Write-Output "code identity: $codeIdentity"
    Write-Output "leaderboard: $leaderboardOut"
}
catch {
    if ($preflightStatus -eq "not_run") {
        $preflightStatus = "fail"
    }
    $meta = New-GateMetadata `
        -Status "failed" `
        -GatePass $false `
        -PublicPerformanceEvidence $false `
        -BenchmarkEvidenceVerified $false `
        -ErrorMessage $_.Exception.Message
    Write-JsonUtf8NoBom -Data $meta -Path $gateMeta -Depth 4
    Write-Output "gate dir: $gateDir"
    Write-Output "gate metadata: $gateMeta"
    Write-Error "PREPUBLISH BENCHMARK GATE: FAIL - $($_.Exception.Message)"
    exit 1
}
