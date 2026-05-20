param(
    [string]$Suffix = $env:MAPU_BENCH_PROJECT_SUFFIX,
    [string]$ModelLabel = $env:MAPU_BENCH_MODEL_LABEL,
    [string]$LauncherMetadata = $env:MAPU_BENCH_LAUNCHER_METADATA,
    [switch]$Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location -LiteralPath $repoRoot

function Get-JsonCount([string]$path) {
    if (-not (Test-Path -LiteralPath $path)) {
        return 0
    }
    return (Get-ChildItem -LiteralPath $path -Filter "*.json" |
        Where-Object { $_.BaseName -notlike "_*" } |
        Measure-Object).Count
}

function Get-FirstRegexMatch([string]$path, [string]$pattern) {
    if (-not (Test-Path -LiteralPath $path)) {
        return $null
    }
    foreach ($line in Get-Content -LiteralPath $path) {
        if ($line -match $pattern) {
            return $Matches[1]
        }
    }
    return $null
}

function Get-WorkerPids([string]$path) {
    $pids = @()
    if (-not (Test-Path -LiteralPath $path)) {
        return $pids
    }
    foreach ($line in Get-Content -LiteralPath $path) {
        if ($line -match "Started\s+(.+?)\s+PID=(\d+)") {
            $pids += [pscustomobject]@{
                lane = $Matches[1]
                pid = [int]$Matches[2]
                running = [bool](Get-Process -Id ([int]$Matches[2]) -ErrorAction SilentlyContinue)
            }
        }
    }
    return $pids
}

function Read-JsonFile([string]$path) {
    try {
        return Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
    }
    catch {
        throw "Could not read JSON metadata: $path"
    }
}

$launcherMeta = $null
$launcherMetaPath = $null
if (-not [string]::IsNullOrWhiteSpace($LauncherMetadata)) {
    $launcherMetaPath = if ([System.IO.Path]::IsPathRooted($LauncherMetadata)) {
        $LauncherMetadata
    }
    else {
        Join-Path $repoRoot $LauncherMetadata
    }
    if (-not (Test-Path -LiteralPath $launcherMetaPath)) {
        throw "Launcher metadata not found: $launcherMetaPath"
    }
    $launcherMeta = Read-JsonFile $launcherMetaPath
}
elseif (-not $Suffix) {
    $latestLauncher = Get-ChildItem "logs/benchmarks" -Filter "prepublish_gate_launcher_*.json" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($latestLauncher) {
        $launcherMetaPath = $latestLauncher.FullName
        $launcherMeta = Read-JsonFile $launcherMetaPath
    }
}

if ($launcherMeta -and $launcherMeta.project_suffix) {
    $launcherSuffix = [string]$launcherMeta.project_suffix
    if ($Suffix -and $Suffix -ne $launcherSuffix) {
        throw "Suffix '$Suffix' does not match launcher metadata project_suffix '$launcherSuffix'"
    }
    $Suffix = $launcherSuffix
}
$modelLabel = $ModelLabel
if ($launcherMeta -and $launcherMeta.model_label) {
    $modelLabel = [string]$launcherMeta.model_label
}
if ([string]::IsNullOrWhiteSpace($modelLabel)) {
    $modelLabel = "qwen06"
}

if (-not $Suffix) {
    $latestGate = Get-ChildItem "logs/benchmarks" -Directory -Filter "prepublish_gate_*" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($latestGate -and $latestGate.Name -match "^prepublish_gate_(.+)$") {
        $Suffix = "prepublish_$($Matches[1])"
    }
}
if (-not $Suffix) {
    $Suffix = "v2"
}

$locomoTotal = 1540
$locomoDone = Get-JsonCount "results/locomo/predicted_mapu_fullsweep_${modelLabel}_locomo_$Suffix"

$longmemTotal = 500
$longmemDone = Get-JsonCount "results/longmemeval/predicted_mapu_fullsweep_${modelLabel}_longmemeval_$Suffix"

$beamExpected = @(
    [pscustomobject]@{
        project = "predicted_mapu_fullsweep_${modelLabel}_beam_100k_$Suffix"
        total = 400
    },
    [pscustomobject]@{
        project = "predicted_mapu_fullsweep_${modelLabel}_beam_500k_$Suffix"
        total = 700
    },
    [pscustomobject]@{
        project = "predicted_mapu_fullsweep_${modelLabel}_beam_1m_$Suffix"
        total = 700
    },
    [pscustomobject]@{
        project = "predicted_mapu_fullsweep_${modelLabel}_beam_10m_$Suffix"
        total = 200
    }
)
$beamStatus = @()
foreach ($beam in $beamExpected) {
    $beamStatus += [pscustomobject]@{
        project = $beam.project
        completed = Get-JsonCount ("results/beam/{0}" -f $beam.project)
        total = $beam.total
    }
}

$latestGate = $null
if ($Suffix -match "^prepublish_(.+)$") {
    $latestGate = Join-Path "logs/benchmarks" ("prepublish_gate_{0}" -f $Matches[1])
}
$latestOut = if ($latestGate -and (Test-Path -LiteralPath $latestGate)) {
    Get-Item (Join-Path $latestGate "sweep.out.log") -ErrorAction SilentlyContinue
} else {
    Get-ChildItem "logs/benchmarks" -Filter "full_sweeps_*.out.log" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
}
$latestErr = if ($latestGate -and (Test-Path -LiteralPath $latestGate)) {
    Get-Item (Join-Path $latestGate "sweep.err.log") -ErrorAction SilentlyContinue
} else {
    Get-ChildItem "logs/benchmarks" -Filter "full_sweeps_*.err.log" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
}

$codeIdentityPath = if ($latestGate) { Join-Path $latestGate "code_identity.txt" } else { $null }
$gateMetaPath = if ($latestGate) { Join-Path $latestGate "gate_meta.json" } else { $null }
$gateMeta = $null
if ($gateMetaPath -and (Test-Path -LiteralPath $gateMetaPath)) {
    try {
        $gateMeta = Get-Content -LiteralPath $gateMetaPath -Raw | ConvertFrom-Json
    }
    catch {
        $gateMeta = $null
    }
}

$codeSha = if ($codeIdentityPath) { Get-FirstRegexMatch $codeIdentityPath "^sha=(.+)$" } else { $null }
$codeWorktree = if ($codeIdentityPath) { Get-FirstRegexMatch $codeIdentityPath "^worktree=(.+)$" } else { $null }
$currentSha = (& git rev-parse HEAD 2>$null)
if ($LASTEXITCODE -ne 0) { $currentSha = $null }
$currentShaMatches = if ($codeSha -and $currentSha) { $codeSha -eq $currentSha } else { $false }
$workerPids = if ($latestOut) { Get-WorkerPids $latestOut.FullName } else { @() }
if ($null -eq $workerPids) {
    $workerPids = @()
}
else {
    $workerPids = @($workerPids)
}
$activeWorkerCount = @($workerPids | Where-Object { $_.running }).Count
$allBeamComplete = @($beamStatus | Where-Object { $_.completed -lt $_.total }).Count -eq 0
$allCountsComplete = ($locomoDone -ge $locomoTotal) -and ($longmemDone -ge $longmemTotal) -and $allBeamComplete
$gatePass = if ($gateMeta -and $null -ne $gateMeta.gate_pass) { [bool]$gateMeta.gate_pass } else { $false }
$gateStatus = if ($gateMeta -and $gateMeta.status) { [string]$gateMeta.status } else { $null }
$benchmarkEvidenceVerified = if ($gateMeta -and $null -ne $gateMeta.benchmark_evidence_verified) { [bool]$gateMeta.benchmark_evidence_verified } else { $false }
$gatePublicEvidence = if ($gateMeta -and $null -ne $gateMeta.public_performance_evidence) { [bool]$gateMeta.public_performance_evidence } else { $false }
$publicEvidence = $gatePass -and $gatePublicEvidence -and $benchmarkEvidenceVerified -and $allCountsComplete -and $currentShaMatches
$launcherPid = if ($launcherMeta -and $null -ne $launcherMeta.pid) { [int]$launcherMeta.pid } else { $null }
$launcherRunning = if ($launcherPid) { [bool](Get-Process -Id $launcherPid -ErrorAction SilentlyContinue) } else { $false }
$resumeCommand = if ($Suffix -and $Suffix -match "^prepublish_\d{8}_\d{6}$") {
    if ($launcherMeta -and $launcherMeta.resume_command) {
        [string]$launcherMeta.resume_command
    }
    else {
        "powershell -NoProfile -ExecutionPolicy Bypass -File tools\prepublish_benchmark_gate.ps1 -Parallel -MaxParallel 3 -IdleTimeoutMinutes 20 -ProjectSuffix $Suffix -Resume"
    }
} else {
    $null
}

$summary = [ordered]@{
    suffix = $Suffix
    model_label = $modelLabel
    gate_dir = $latestGate
    code_sha = $codeSha
    current_sha = $currentSha
    current_sha_matches = $currentShaMatches
    worktree = $codeWorktree
    launcher_metadata = $launcherMetaPath
    launcher_pid = $launcherPid
    launcher_running = $launcherRunning
    gate_status = $gateStatus
    gate_meta_present = [bool]$gateMeta
    gate_pass = $gatePass
    benchmark_evidence_verified = $benchmarkEvidenceVerified
    active_worker_count = $activeWorkerCount
    public_performance_evidence = $publicEvidence
    locomo = [ordered]@{ completed = $locomoDone; total = $locomoTotal }
    longmemeval = [ordered]@{ completed = $longmemDone; total = $longmemTotal }
    beam = $beamStatus
    workers = @($workerPids)
    resume_command = $resumeCommand
}

if ($Json) {
    $summary | ConvertTo-Json -Depth 6
    exit 0
}

Write-Output ("Project suffix: {0}" -f $Suffix)
Write-Output ("Model label: {0}" -f $modelLabel)
if ($launcherMetaPath) {
    Write-Output ("Launcher metadata: {0}" -f $launcherMetaPath)
    if ($launcherPid) {
        Write-Output ("Launcher process: PID={0}; running={1}" -f $launcherPid, $launcherRunning)
    }
}
if ($latestGate) {
    Write-Output ("Gate directory: {0}" -f $latestGate)
}
if ($codeSha) {
    Write-Output ("Code identity: sha={0}; worktree={1}" -f $codeSha, $codeWorktree)
}
if ($currentSha) {
    Write-Output ("Current HEAD: {0}; matches gate code identity: {1}" -f $currentSha, $currentShaMatches)
}
if ($gateMeta) {
    Write-Output ("Gate metadata: present; status={0}; gate_pass={1}; verified={2}; public_evidence={3}" -f $gateStatus, $gatePass, $benchmarkEvidenceVerified, $gatePublicEvidence)
}
else {
    Write-Output "Gate metadata: missing or unreadable"
}
if ($resumeCommand) {
    Write-Output ("Resume command: {0}" -f $resumeCommand)
}
Write-Output ("Worker status: {0} active / {1} recorded" -f $activeWorkerCount, @($workerPids).Count)
if (@($workerPids).Count -gt 0) {
    $workerPids | Format-Table -AutoSize | Out-String | Write-Output
}

Write-Output ("LoCoMo: {0}/{1}" -f $locomoDone, $locomoTotal)
Write-Output ("LongMemEval: {0}/{1}" -f $longmemDone, $longmemTotal)
Write-Output "BEAM:"
$beamStatus | Format-Table -AutoSize | Out-String | Write-Output

if ($publicEvidence) {
    Write-Output "Verdict: COMPLETE public benchmark evidence for this suffix."
}
elseif ($activeWorkerCount -eq 0 -and -not $gatePass) {
    Write-Output "Verdict: STALE/INCOMPLETE. No benchmark workers are active and no passing gate metadata exists."
}
elseif ($activeWorkerCount -eq 0 -and -not $allCountsComplete) {
    Write-Output "Verdict: INCOMPLETE. No benchmark workers are active and result counts are partial."
}
else {
    Write-Output "Verdict: RUNNING/UNPROVEN. Do not use this as public performance evidence until the full prepublish gate passes."
}

if ($latestOut) {
    Write-Output ("Latest stdout log: {0}" -f $latestOut.Name)
    Get-Content $latestOut.FullName -Tail 10
}
if ($latestErr) {
    Write-Output ("Latest stderr log: {0}" -f $latestErr.Name)
    Get-Content $latestErr.FullName -Tail 10
}
