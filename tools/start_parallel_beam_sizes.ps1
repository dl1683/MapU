Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location -LiteralPath $repoRoot

$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Python executable not found: $python"
}

$logDir = Join-Path $repoRoot "logs\benchmarks"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$env:OPENAI_API_KEY = "dummy"
$env:OPENAI_BASE_URL = "http://localhost:11434/v1"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:MAPU_BENCH_CONTEXT_LIMIT = "40"
Remove-Item Env:\MAPU_BENCH_SKIP_INGEST -ErrorAction SilentlyContinue
$env:TQDM_DISABLE = "1"
$env:MAPU_LLM_MAX_TOKENS = "192"
$env:MAPU_LLM_STRUCTURED_MAX_TOKENS = "128"
$env:MAPU_LLM_JUDGE_MAX_TOKENS = "64"

$jobs = @(
    @{
        Name = "beam_full_500k_parallel"
        Project = "mapu_fullsweep_qwen06_beam_500k_v2"
        Size = "500K"
    },
    @{
        Name = "beam_full_1m_parallel"
        Project = "mapu_fullsweep_qwen06_beam_1m_v2"
        Size = "1M"
    },
    @{
        Name = "beam_full_10m_parallel"
        Project = "mapu_fullsweep_qwen06_beam_10m_v2"
        Size = "10M"
    }
)

foreach ($job in $jobs) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $stdoutLog = Join-Path $logDir ("{0}_{1}.out.log" -f $job.Name, $stamp)
    $stderrLog = Join-Path $logDir ("{0}_{1}.err.log" -f $job.Name, $stamp)

    $argList = @(
        "tools/run_mem0_benchmark_with_mapu.py", "beam",
        "--project-name", $job.Project,
        "--answerer-model", "qwen3:0.6b",
        "--judge-model", "qwen3:0.6b",
        "--provider", "openai",
        "--judge-provider", "openai",
        "--backend", "oss",
        "--mem0-host", "http://localhost:8000",
        "--chat-sizes", $job.Size,
        "--conversations", "0-99",
        "--top-k", "200",
        "--top-k-cutoffs", "10,50,200",
        "--max-workers", "8",
        "--rpm", "4000",
        "--resume"
    )

    $proc = Start-Process -FilePath $python `
        -ArgumentList $argList `
        -WorkingDirectory $repoRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutLog `
        -RedirectStandardError $stderrLog `
        -PassThru

    Write-Output ("Started {0} PID={1}" -f $job.Name, $proc.Id)
    Write-Output ("  stdout: {0}" -f $stdoutLog)
    Write-Output ("  stderr: {0}" -f $stderrLog)
}
