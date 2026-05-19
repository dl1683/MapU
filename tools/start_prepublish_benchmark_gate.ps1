param(
    [switch]$Parallel,
    [int]$MaxParallel = 3,
    [int]$LaneTimeoutMinutes = 240,
    [int]$IdleTimeoutMinutes = 20,
    [string]$ProjectSuffix = "",
    [string]$AnswererModel = "qwen3:0.6b",
    [string]$JudgeModel = "",
    [string]$Provider = "openai",
    [string]$JudgeProvider = "",
    [string]$ModelBaseUrl = "http://localhost:11434/v1",
    [string]$ModelLabel = "",
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
$gateProjectSuffix = if (-not [string]::IsNullOrWhiteSpace($ProjectSuffix)) {
    $ProjectSuffix
}
else {
    "prepublish_$stamp"
}
if ($gateProjectSuffix -notmatch "^prepublish_\d{8}_\d{6}$") {
    throw "ProjectSuffix must be blank or match prepublish_yyyyMMdd_HHmmss"
}
if ([string]::IsNullOrWhiteSpace($AnswererModel)) {
    throw "AnswererModel must not be blank"
}
if ([string]::IsNullOrWhiteSpace($JudgeModel)) {
    $JudgeModel = $AnswererModel
}
if ([string]::IsNullOrWhiteSpace($Provider)) {
    throw "Provider must not be blank"
}
if ([string]::IsNullOrWhiteSpace($JudgeProvider)) {
    $JudgeProvider = $Provider
}
if ([string]::IsNullOrWhiteSpace($ModelBaseUrl)) {
    throw "ModelBaseUrl must not be blank"
}
if ([string]::IsNullOrWhiteSpace($ModelLabel)) {
    $ModelLabel = ($AnswererModel.ToLowerInvariant() -replace "[^a-z0-9]+", "_").Trim("_")
}
if ($ModelLabel -notmatch "^[A-Za-z0-9_-]+$") {
    throw "ModelLabel must contain only letters, numbers, underscores, or hyphens"
}
if ($Resume -and [string]::IsNullOrWhiteSpace($ProjectSuffix)) {
    throw "Resume requires -ProjectSuffix prepublish_yyyyMMdd_HHmmss so checkpoint reuse is explicit"
}

$stdoutLog = Join-Path $logDir "prepublish_gate_launcher_${stamp}.out.log"
$stderrLog = Join-Path $logDir "prepublish_gate_launcher_${stamp}.err.log"
$launcherMeta = Join-Path $logDir "prepublish_gate_launcher_${stamp}.json"
$gateDir = Join-Path $logDir ($gateProjectSuffix -replace "^prepublish_", "prepublish_gate_")

function Write-JsonUtf8NoBom {
    param(
        [object]$Data,
        [string]$Path,
        [int]$Depth = 6
    )

    $absolutePath = [System.IO.Path]::GetFullPath($Path)
    $parent = [System.IO.Path]::GetDirectoryName($absolutePath)
    if (-not [string]::IsNullOrWhiteSpace($parent)) {
        [System.IO.Directory]::CreateDirectory($parent) | Out-Null
    }
    $json = $Data | ConvertTo-Json -Depth $Depth
    $encoding = New-Object System.Text.UTF8Encoding -ArgumentList $false
    [System.IO.File]::WriteAllText($absolutePath, ($json + [Environment]::NewLine), $encoding)
}

$argList = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $runner,
    "-MaxParallel", $MaxParallel,
    "-LaneTimeoutMinutes", $LaneTimeoutMinutes,
    "-IdleTimeoutMinutes", $IdleTimeoutMinutes,
    "-ProjectSuffix", $gateProjectSuffix,
    "-AnswererModel", $AnswererModel,
    "-JudgeModel", $JudgeModel,
    "-Provider", $Provider,
    "-JudgeProvider", $JudgeProvider,
    "-ModelBaseUrl", $ModelBaseUrl,
    "-ModelLabel", $ModelLabel
)
if ($Parallel) {
    $argList += "-Parallel"
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

$gitSha = (& git rev-parse HEAD 2>$null)
if ($LASTEXITCODE -ne 0) { $gitSha = "unknown" }
$resumeCommand = "powershell -NoProfile -ExecutionPolicy Bypass -File tools\prepublish_benchmark_gate.ps1 -Parallel -MaxParallel $MaxParallel -IdleTimeoutMinutes $IdleTimeoutMinutes -LaneTimeoutMinutes $LaneTimeoutMinutes -ProjectSuffix $gateProjectSuffix -AnswererModel $AnswererModel -JudgeModel $JudgeModel -Provider $Provider -JudgeProvider $JudgeProvider -ModelBaseUrl $ModelBaseUrl -ModelLabel $ModelLabel -Resume"
$progressCommand = "powershell -NoProfile -ExecutionPolicy Bypass -File tools\check_full_sweep_progress.ps1 -LauncherMetadata $launcherMeta -Json"
$meta = [ordered]@{
    started_at = (Get-Date -Format "o")
    pid = $proc.Id
    git_sha = $gitSha
    project_suffix = $gateProjectSuffix
    gate_dir = $gateDir
    parallel = $Parallel.IsPresent
    max_parallel = $MaxParallel
    lane_timeout_minutes = $LaneTimeoutMinutes
    idle_timeout_minutes = $IdleTimeoutMinutes
    resume = $Resume.IsPresent
    answerer_model = $AnswererModel
    judge_model = $JudgeModel
    provider = $Provider
    judge_provider = $JudgeProvider
    model_base_url = $ModelBaseUrl
    model_label = $ModelLabel
    stdout_log = $stdoutLog
    stderr_log = $stderrLog
    launcher_metadata = $launcherMeta
    command_line = @("powershell.exe") + $argList
    progress_command = $progressCommand
    resume_command = $resumeCommand
}
Write-JsonUtf8NoBom -Data $meta -Path $launcherMeta

Write-Output ("Started prepublish benchmark gate PID={0}" -f $proc.Id)
Write-Output ("parallel: {0}" -f $Parallel.IsPresent)
Write-Output ("max_parallel: {0}" -f $MaxParallel)
Write-Output ("lane_timeout_minutes: {0}" -f $LaneTimeoutMinutes)
Write-Output ("idle_timeout_minutes: {0}" -f $IdleTimeoutMinutes)
Write-Output ("project_suffix: {0}" -f $gateProjectSuffix)
Write-Output ("answerer_model: {0}" -f $AnswererModel)
Write-Output ("judge_model: {0}" -f $JudgeModel)
Write-Output ("model_base_url: {0}" -f $ModelBaseUrl)
Write-Output ("model_label: {0}" -f $ModelLabel)
Write-Output ("resume: {0}" -f $Resume.IsPresent)
Write-Output ("stdout log: {0}" -f $stdoutLog)
Write-Output ("stderr log: {0}" -f $stderrLog)
Write-Output ("launcher metadata: {0}" -f $launcherMeta)
Write-Output ("progress command: {0}" -f $progressCommand)
Write-Output ("resume command: {0}" -f $resumeCommand)
