param(
    [string]$Suffix = $env:MAPU_BENCH_PROJECT_SUFFIX,
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
$locomoDone = Get-JsonCount "results/locomo/predicted_mapu_fullsweep_qwen06_locomo_$Suffix"

$longmemTotal = 500
$longmemDone = Get-JsonCount "results/longmemeval/predicted_mapu_fullsweep_qwen06_longmemeval_$Suffix"

$beamDirs = @(
    "predicted_mapu_fullsweep_qwen06_beam_100k_$Suffix",
    "predicted_mapu_fullsweep_qwen06_beam_500k_$Suffix",
    "predicted_mapu_fullsweep_qwen06_beam_1m_$Suffix",
    "predicted_mapu_fullsweep_qwen06_beam_10m_$Suffix"
)
$beamStatus = @()
foreach ($d in $beamDirs) {
    $beamStatus += [pscustomobject]@{
        project = $d
        completed = Get-JsonCount ("results/beam/{0}" -f $d)
        total = 500
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
$workerPids = if ($latestOut) { Get-WorkerPids $latestOut.FullName } else { @() }
$activeWorkerCount = @($workerPids | Where-Object { $_.running }).Count
$allBeamComplete = @($beamStatus | Where-Object { $_.completed -lt $_.total }).Count -eq 0
$allCountsComplete = ($locomoDone -ge $locomoTotal) -and ($longmemDone -ge $longmemTotal) -and $allBeamComplete
$gatePass = if ($gateMeta -and $null -ne $gateMeta.gate_pass) { [bool]$gateMeta.gate_pass } else { $false }
$publicEvidence = $gatePass -and $allCountsComplete

$summary = [ordered]@{
    suffix = $Suffix
    gate_dir = $latestGate
    code_sha = $codeSha
    worktree = $codeWorktree
    gate_meta_present = [bool]$gateMeta
    gate_pass = $gatePass
    active_worker_count = $activeWorkerCount
    public_performance_evidence = $publicEvidence
    locomo = [ordered]@{ completed = $locomoDone; total = $locomoTotal }
    longmemeval = [ordered]@{ completed = $longmemDone; total = $longmemTotal }
    beam = $beamStatus
    workers = $workerPids
}

if ($Json) {
    $summary | ConvertTo-Json -Depth 6
    exit 0
}

Write-Output ("Project suffix: {0}" -f $Suffix)
if ($latestGate) {
    Write-Output ("Gate directory: {0}" -f $latestGate)
}
if ($codeSha) {
    Write-Output ("Code identity: sha={0}; worktree={1}" -f $codeSha, $codeWorktree)
}
if ($gateMeta) {
    Write-Output ("Gate metadata: present; gate_pass={0}" -f $gatePass)
}
else {
    Write-Output "Gate metadata: missing or unreadable"
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
