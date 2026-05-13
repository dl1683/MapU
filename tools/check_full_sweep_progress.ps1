param(
    [string]$Suffix = $env:MAPU_BENCH_PROJECT_SUFFIX
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

Write-Output ("Project suffix: {0}" -f $Suffix)

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
    }
}

Write-Output ("LoCoMo: {0}/{1}" -f $locomoDone, $locomoTotal)
Write-Output ("LongMemEval: {0}/{1}" -f $longmemDone, $longmemTotal)
Write-Output "BEAM:"
$beamStatus | Format-Table -AutoSize | Out-String | Write-Output

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

if ($latestOut) {
    Write-Output ("Latest stdout log: {0}" -f $latestOut.Name)
    Get-Content $latestOut.FullName -Tail 10
}
if ($latestErr) {
    Write-Output ("Latest stderr log: {0}" -f $latestErr.Name)
    Get-Content $latestErr.FullName -Tail 10
}
