Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location -LiteralPath $repoRoot

$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Python executable not found: $python"
}

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

$projectSuffix = $env:MAPU_BENCH_PROJECT_SUFFIX
if (-not $projectSuffix) {
    $projectSuffix = "public_" + (Get-Date -Format "yyyyMMdd_HHmmss")
    $env:MAPU_BENCH_PROJECT_SUFFIX = $projectSuffix
}
Write-Output ("[{0}] Public benchmark project suffix: {1}" -f (Get-Date -Format "s"), $projectSuffix)

function Invoke-Benchmark {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string[]]$Args
    )
    Write-Output ("[{0}] Starting {1}" -f (Get-Date -Format "s"), $Name)
    $tmpOut = [System.IO.Path]::GetTempFileName()
    $tmpErr = [System.IO.Path]::GetTempFileName()
    try {
        $process = Start-Process `
            -FilePath $python `
            -ArgumentList $Args `
            -NoNewWindow `
            -Wait `
            -PassThru `
            -RedirectStandardOutput $tmpOut `
            -RedirectStandardError $tmpErr
        if (Test-Path -LiteralPath $tmpOut) {
            Get-Content -LiteralPath $tmpOut | ForEach-Object { Write-Output $_ }
        }
        if (Test-Path -LiteralPath $tmpErr) {
            Get-Content -LiteralPath $tmpErr | ForEach-Object { Write-Output ("[stderr] {0}" -f $_) }
        }
        $exitCode = $process.ExitCode
    }
    finally {
        Remove-Item -LiteralPath $tmpOut, $tmpErr -Force -ErrorAction SilentlyContinue
    }
    Write-Output ("[{0}] {1} exited with code {2}" -f (Get-Date -Format "s"), $Name, $exitCode)
    if ($exitCode -ne 0) {
        throw "$Name failed with exit code $exitCode"
    }
}

$jobs = @(
    @{
        Name = "locomo_full_qwen06"
        Args = @(
            "tools/run_mem0_benchmark_with_mapu.py", "locomo",
            "--project-name", "mapu_fullsweep_qwen06_locomo_$projectSuffix",
            "--answerer-model", "qwen3:0.6b",
            "--judge-model", "qwen3:0.6b",
            "--provider", "openai",
            "--judge-provider", "openai",
            "--backend", "oss",
            "--mem0-host", "http://localhost:8000",
            "--conversations", "0,1,2,3,4,5,6,7,8,9",
            "--categories", "1,2,3,4",
            "--top-k", "200",
            "--top-k-cutoffs", "10,50,200",
            "--max-workers", "8",
            "--rpm", "4000"
        )
    },
    @{
        Name = "longmemeval_full_qwen06"
        Args = @(
            "tools/run_mem0_benchmark_with_mapu.py", "longmemeval",
            "--project-name", "mapu_fullsweep_qwen06_longmemeval_$projectSuffix",
            "--answerer-model", "qwen3:0.6b",
            "--judge-model", "qwen3:0.6b",
            "--provider", "openai",
            "--judge-provider", "openai",
            "--backend", "oss",
            "--mem0-host", "http://localhost:8000",
            "--all-questions",
            "--top-k", "200",
            "--top-k-cutoffs", "10,50,200",
            "--max-workers", "8",
            "--rpm", "4000"
        )
    },
    @{
        Name = "beam_full_100k_qwen06"
        Args = @(
            "tools/run_mem0_benchmark_with_mapu.py", "beam",
            "--project-name", "mapu_fullsweep_qwen06_beam_100k_$projectSuffix",
            "--answerer-model", "qwen3:0.6b",
            "--judge-model", "qwen3:0.6b",
            "--provider", "openai",
            "--judge-provider", "openai",
            "--backend", "oss",
            "--mem0-host", "http://localhost:8000",
            "--chat-sizes", "100K",
            "--conversations", "0-99",
            "--top-k", "200",
            "--top-k-cutoffs", "10,50,200",
            "--max-workers", "8",
            "--rpm", "4000"
        )
    },
    @{
        Name = "beam_full_500k_qwen06"
        Args = @(
            "tools/run_mem0_benchmark_with_mapu.py", "beam",
            "--project-name", "mapu_fullsweep_qwen06_beam_500k_$projectSuffix",
            "--answerer-model", "qwen3:0.6b",
            "--judge-model", "qwen3:0.6b",
            "--provider", "openai",
            "--judge-provider", "openai",
            "--backend", "oss",
            "--mem0-host", "http://localhost:8000",
            "--chat-sizes", "500K",
            "--conversations", "0-99",
            "--top-k", "200",
            "--top-k-cutoffs", "10,50,200",
            "--max-workers", "8",
            "--rpm", "4000"
        )
    },
    @{
        Name = "beam_full_1m_qwen06"
        Args = @(
            "tools/run_mem0_benchmark_with_mapu.py", "beam",
            "--project-name", "mapu_fullsweep_qwen06_beam_1m_$projectSuffix",
            "--answerer-model", "qwen3:0.6b",
            "--judge-model", "qwen3:0.6b",
            "--provider", "openai",
            "--judge-provider", "openai",
            "--backend", "oss",
            "--mem0-host", "http://localhost:8000",
            "--chat-sizes", "1M",
            "--conversations", "0-99",
            "--top-k", "200",
            "--top-k-cutoffs", "10,50,200",
            "--max-workers", "8",
            "--rpm", "4000"
        )
    },
    @{
        Name = "beam_full_10m_qwen06"
        Args = @(
            "tools/run_mem0_benchmark_with_mapu.py", "beam",
            "--project-name", "mapu_fullsweep_qwen06_beam_10m_$projectSuffix",
            "--answerer-model", "qwen3:0.6b",
            "--judge-model", "qwen3:0.6b",
            "--provider", "openai",
            "--judge-provider", "openai",
            "--backend", "oss",
            "--mem0-host", "http://localhost:8000",
            "--chat-sizes", "10M",
            "--conversations", "0-99",
            "--top-k", "200",
            "--top-k-cutoffs", "10,50,200",
            "--max-workers", "8",
            "--rpm", "4000"
        )
    }
)

foreach ($job in $jobs) {
    Invoke-Benchmark -Name $job.Name -Args $job.Args
}

Write-Output ("[{0}] All benchmark sweeps completed." -f (Get-Date -Format "s"))
