param(
    [string]$BenchmarkMem0HostArg = "http://localhost:8000",
    [string]$AnswererModel = "qwen3:0.6b",
    [string]$JudgeModel = "",
    [string]$Provider = "openai",
    [string]$JudgeProvider = "",
    [string]$ModelBaseUrl = "http://localhost:11434/v1",
    [string]$ModelApiKey = "",
    [string]$ModelLabel = "",
    [switch]$Resume
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($BenchmarkMem0HostArg)) {
    throw "BenchmarkMem0HostArg must not be blank"
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
if ([string]::IsNullOrWhiteSpace($ModelLabel)) {
    throw "ModelLabel must not be blank"
}
if ($ModelLabel -notmatch "^[A-Za-z0-9_-]+$") {
    throw "ModelLabel must contain only letters, numbers, underscores, or hyphens"
}
if ([string]::IsNullOrWhiteSpace($ModelApiKey)) {
    $candidateKeyNames = @("GEMINI_API_KEY", "GOOGLE_API_KEY", "MAPU_LLM_API_KEY", "OPENAI_API_KEY")
    foreach ($candidateKeyName in $candidateKeyNames) {
        foreach ($target in @("Process", "User", "Machine")) {
            $candidateKey = [Environment]::GetEnvironmentVariable($candidateKeyName, $target)
            if (-not [string]::IsNullOrWhiteSpace($candidateKey)) {
                $ModelApiKey = $candidateKey
                break
            }
        }
        if (-not [string]::IsNullOrWhiteSpace($ModelApiKey)) {
            break
        }
    }
}

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location -LiteralPath $repoRoot

$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Python executable not found: $python"
}

$env:OPENAI_API_KEY = if ([string]::IsNullOrWhiteSpace($ModelApiKey)) { "dummy" } else { $ModelApiKey }
$env:OPENAI_BASE_URL = $ModelBaseUrl
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:MAPU_BENCH_CONTEXT_LIMIT = "40"
Remove-Item Env:\MAPU_BENCH_SKIP_INGEST -ErrorAction SilentlyContinue
$env:TQDM_DISABLE = "1"
$env:MAPU_LLM_MAX_TOKENS = "192"
$env:MAPU_LLM_STRUCTURED_MAX_TOKENS = "128"
$env:MAPU_LLM_JUDGE_MAX_TOKENS = "64"

$projectSuffix = $env:MAPU_BENCH_PROJECT_SUFFIX
if (-not $projectSuffix) {
    $projectSuffix = "public_" + (Get-Date -Format "yyyyMMdd_HHmmss")
    $env:MAPU_BENCH_PROJECT_SUFFIX = $projectSuffix
}
$env:MAPU_BENCH_MODEL_LABEL = $ModelLabel
Write-Output ("[{0}] Public benchmark project suffix: {1}" -f (Get-Date -Format "s"), $projectSuffix)
Write-Output ("[{0}] Answerer model: {1}" -f (Get-Date -Format "s"), $AnswererModel)
Write-Output ("[{0}] Judge model: {1}" -f (Get-Date -Format "s"), $JudgeModel)
Write-Output ("[{0}] Model provider: {1}; judge provider: {2}" -f (Get-Date -Format "s"), $Provider, $JudgeProvider)
Write-Output ("[{0}] Model base URL: {1}" -f (Get-Date -Format "s"), $ModelBaseUrl)
Write-Output ("[{0}] Model API key present: {1}" -f (Get-Date -Format "s"), (-not [string]::IsNullOrWhiteSpace($ModelApiKey)))
Write-Output ("[{0}] Benchmark model label: {1}" -f (Get-Date -Format "s"), $ModelLabel)
Write-Output ("[{0}] Benchmark mem0 host argument: {1}" -f (Get-Date -Format "s"), $BenchmarkMem0HostArg)
Write-Output ("[{0}] Resume existing benchmark checkpoints: {1}" -f (Get-Date -Format "s"), $Resume.IsPresent)

$logDir = Join-Path $repoRoot "logs\benchmarks\sweep_$projectSuffix"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Write-Output ("[{0}] Lane artifact directory: {1}" -f (Get-Date -Format "s"), $logDir)

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

function Write-LaneMetadata {
    param(
        [string]$Name,
        [string[]]$Args,
        [string]$StdoutLog,
        [string]$StderrLog,
        [datetime]$StartedAt,
        [datetime]$FinishedAt,
        [object]$ExitCode,
        [string]$FailureReason = ""
    )

    $meta = [ordered]@{
        name = $Name
        args = @($Args)
        stdout_log = $StdoutLog
        stderr_log = $StderrLog
        started_at = $StartedAt.ToString("o")
        finished_at = $FinishedAt.ToString("o")
        elapsed_seconds = [math]::Round(($FinishedAt - $StartedAt).TotalSeconds, 3)
        exit_code = $ExitCode
        failure_reason = $FailureReason
    }
    $metaPath = Join-Path $logDir ("{0}.meta.json" -f $Name)
    Write-JsonUtf8NoBom -Data $meta -Path $metaPath -Depth 6
    Write-Output ("[{0}] {1} metadata: {2}" -f (Get-Date -Format "s"), $Name, $metaPath)
}

function Invoke-Benchmark {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string[]]$Args
    )
    Write-Output ("[{0}] Starting {1}" -f (Get-Date -Format "s"), $Name)
    $stdoutLog = Join-Path $logDir ("{0}.out.log" -f $Name)
    $stderrLog = Join-Path $logDir ("{0}.err.log" -f $Name)
    $startedAt = Get-Date
    $exitCode = $null
    $failureReason = ""
    try {
        $process = Start-Process `
            -FilePath $python `
            -ArgumentList $Args `
            -NoNewWindow `
            -Wait `
            -PassThru `
            -RedirectStandardOutput $stdoutLog `
            -RedirectStandardError $stderrLog
        if (Test-Path -LiteralPath $stdoutLog) {
            Get-Content -LiteralPath $stdoutLog | ForEach-Object { Write-Output $_ }
        }
        if (Test-Path -LiteralPath $stderrLog) {
            Get-Content -LiteralPath $stderrLog | ForEach-Object { Write-Output ("[stderr] {0}" -f $_) }
        }
        $exitCode = $process.ExitCode
    }
    catch {
        $failureReason = $_.Exception.Message
        throw
    }
    finally {
        $finishedAt = Get-Date
        Write-LaneMetadata `
            -Name $Name `
            -Args $Args `
            -StdoutLog $stdoutLog `
            -StderrLog $stderrLog `
            -StartedAt $startedAt `
            -FinishedAt $finishedAt `
            -ExitCode $exitCode `
            -FailureReason $failureReason
    }
    Write-Output ("[{0}] {1} exited with code {2}; stdout={3}; stderr={4}" -f (Get-Date -Format "s"), $Name, $exitCode, $stdoutLog, $stderrLog)
    if ($exitCode -ne 0) {
        throw "$Name failed with exit code $exitCode; stdout=$stdoutLog; stderr=$stderrLog"
    }
}

$jobs = @(
    @{
        Name = "locomo_full_$ModelLabel"
        Args = @(
            "tools/run_mem0_benchmark_with_mapu.py", "locomo",
            "--project-name", "mapu_fullsweep_${ModelLabel}_locomo_$projectSuffix",
            "--answerer-model", $AnswererModel,
            "--judge-model", $JudgeModel,
            "--provider", $Provider,
            "--judge-provider", $JudgeProvider,
            "--backend", "oss",
            "--mem0-host", $BenchmarkMem0HostArg,
            "--conversations", "0,1,2,3,4,5,6,7,8,9",
            "--categories", "1,2,3,4",
            "--top-k", "200",
            "--top-k-cutoffs", "10,50,200",
            "--max-workers", "8",
            "--rpm", "4000"
        )
    },
    @{
        Name = "longmemeval_full_$ModelLabel"
        Args = @(
            "tools/run_mem0_benchmark_with_mapu.py", "longmemeval",
            "--project-name", "mapu_fullsweep_${ModelLabel}_longmemeval_$projectSuffix",
            "--answerer-model", $AnswererModel,
            "--judge-model", $JudgeModel,
            "--provider", $Provider,
            "--judge-provider", $JudgeProvider,
            "--backend", "oss",
            "--mem0-host", $BenchmarkMem0HostArg,
            "--all-questions",
            "--top-k", "200",
            "--top-k-cutoffs", "10,50,200",
            "--max-workers", "8",
            "--rpm", "4000"
        )
    },
    @{
        Name = "beam_full_100k_$ModelLabel"
        Args = @(
            "tools/run_mem0_benchmark_with_mapu.py", "beam",
            "--project-name", "mapu_fullsweep_${ModelLabel}_beam_100k_$projectSuffix",
            "--answerer-model", $AnswererModel,
            "--judge-model", $JudgeModel,
            "--provider", $Provider,
            "--judge-provider", $JudgeProvider,
            "--backend", "oss",
            "--mem0-host", $BenchmarkMem0HostArg,
            "--chat-sizes", "100K",
            "--conversations", "0-99",
            "--top-k", "200",
            "--top-k-cutoffs", "10,50,200",
            "--max-workers", "8",
            "--rpm", "4000"
        )
    },
    @{
        Name = "beam_full_500k_$ModelLabel"
        Args = @(
            "tools/run_mem0_benchmark_with_mapu.py", "beam",
            "--project-name", "mapu_fullsweep_${ModelLabel}_beam_500k_$projectSuffix",
            "--answerer-model", $AnswererModel,
            "--judge-model", $JudgeModel,
            "--provider", $Provider,
            "--judge-provider", $JudgeProvider,
            "--backend", "oss",
            "--mem0-host", $BenchmarkMem0HostArg,
            "--chat-sizes", "500K",
            "--conversations", "0-99",
            "--top-k", "200",
            "--top-k-cutoffs", "10,50,200",
            "--max-workers", "8",
            "--rpm", "4000"
        )
    },
    @{
        Name = "beam_full_1m_$ModelLabel"
        Args = @(
            "tools/run_mem0_benchmark_with_mapu.py", "beam",
            "--project-name", "mapu_fullsweep_${ModelLabel}_beam_1m_$projectSuffix",
            "--answerer-model", $AnswererModel,
            "--judge-model", $JudgeModel,
            "--provider", $Provider,
            "--judge-provider", $JudgeProvider,
            "--backend", "oss",
            "--mem0-host", $BenchmarkMem0HostArg,
            "--chat-sizes", "1M",
            "--conversations", "0-99",
            "--top-k", "200",
            "--top-k-cutoffs", "10,50,200",
            "--max-workers", "8",
            "--rpm", "4000"
        )
    },
    @{
        Name = "beam_full_10m_$ModelLabel"
        Args = @(
            "tools/run_mem0_benchmark_with_mapu.py", "beam",
            "--project-name", "mapu_fullsweep_${ModelLabel}_beam_10m_$projectSuffix",
            "--answerer-model", $AnswererModel,
            "--judge-model", $JudgeModel,
            "--provider", $Provider,
            "--judge-provider", $JudgeProvider,
            "--backend", "oss",
            "--mem0-host", $BenchmarkMem0HostArg,
            "--chat-sizes", "10M",
            "--conversations", "0-99",
            "--top-k", "200",
            "--top-k-cutoffs", "10,50,200",
            "--max-workers", "8",
            "--rpm", "4000"
        )
    }
)

if ($Resume) {
    foreach ($job in $jobs) {
        $job.Args = @($job.Args) + "--resume"
    }
}

foreach ($job in $jobs) {
    Invoke-Benchmark -Name $job.Name -Args $job.Args
}

Write-Output ("[{0}] All benchmark sweeps completed." -f (Get-Date -Format "s"))
