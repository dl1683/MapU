param(
    [int]$TimeoutMinutes = 45
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($TimeoutMinutes -lt 1) {
    throw "TimeoutMinutes must be >= 1"
}

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location -LiteralPath $repoRoot

$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$runner = Join-Path $repoRoot "tools\run_mem0_benchmark_with_mapu.py"
if (-not (Test-Path -LiteralPath $python)) { throw "Missing python: $python" }
if (-not (Test-Path -LiteralPath $runner)) { throw "Missing benchmark wrapper: $runner" }
if (-not (Test-Path -LiteralPath (Join-Path $repoRoot ".tmp\memory-benchmarks"))) {
    throw "Missing .tmp\memory-benchmarks; clone https://github.com/mem0ai/memory-benchmarks first."
}

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

$logRoot = Join-Path $repoRoot "logs\benchmarks"
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$suffix = "smoke_$stamp"
$gateDir = Join-Path $logRoot "benchmark_smoke_gate_$stamp"
New-Item -ItemType Directory -Force -Path $gateDir | Out-Null

$env:OPENAI_API_KEY = "dummy"
$env:OPENAI_BASE_URL = "http://localhost:11434/v1"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:TQDM_DISABLE = "1"
$env:MAPU_BENCH_PROJECT_SUFFIX = $suffix
$env:MAPU_BENCH_CONTEXT_LIMIT = "20"
$env:MAPU_LLM_MAX_TOKENS = "96"
$env:MAPU_LLM_STRUCTURED_MAX_TOKENS = "80"
$env:MAPU_LLM_JUDGE_MAX_TOKENS = "48"
Remove-Item Env:\MAPU_BENCH_SKIP_INGEST -ErrorAction SilentlyContinue

$gitSha = (& git rev-parse HEAD 2>$null)
if ($LASTEXITCODE -ne 0) { $gitSha = "unknown" }
$dirty = (& git status --porcelain 2>$null)
if ($LASTEXITCODE -ne 0) { $dirty = "" }
$dirtyFlag = if ([string]::IsNullOrWhiteSpace($dirty)) { "clean" } else { "dirty" }

$metaPath = Join-Path $gateDir "gate_meta.json"
$codeIdentity = Join-Path $gateDir "code_identity.txt"
Write-TextUtf8NoBom -Path $codeIdentity -Text "sha=$gitSha`nworktree=$dirtyFlag`ntimestamp=$stamp`nsmoke_only=true`ntimeout_minutes=$TimeoutMinutes"

$jobs = @(
    @{
        Name = "locomo_smoke_qwen06"
        Args = @(
            "locomo",
            "--project-name", "mapu_smoke_qwen06_locomo_$suffix",
            "--answerer-model", "qwen3:0.6b",
            "--judge-model", "qwen3:0.6b",
            "--provider", "openai",
            "--judge-provider", "openai",
            "--backend", "oss",
            "--mem0-host", "http://localhost:8000",
            "--conversations", "0",
            "--categories", "1",
            "--max-questions", "1",
            "--top-k", "20",
            "--top-k-cutoffs", "10",
            "--max-workers", "1",
            "--rpm", "4000"
        )
    },
    @{
        Name = "longmemeval_smoke_qwen06"
        Args = @(
            "longmemeval",
            "--project-name", "mapu_smoke_qwen06_longmemeval_$suffix",
            "--answerer-model", "qwen3:0.6b",
            "--judge-model", "qwen3:0.6b",
            "--provider", "openai",
            "--judge-provider", "openai",
            "--backend", "oss",
            "--mem0-host", "http://localhost:8000",
            "--per-type", "1",
            "--question-types", "single-session-user",
            "--top-k", "20",
            "--top-k-cutoffs", "10",
            "--max-workers", "1",
            "--rpm", "4000"
        )
    },
    @{
        Name = "beam_100k_smoke_qwen06"
        Args = @(
            "beam",
            "--project-name", "mapu_smoke_qwen06_beam_100k_$suffix",
            "--answerer-model", "qwen3:0.6b",
            "--judge-model", "qwen3:0.6b",
            "--provider", "openai",
            "--judge-provider", "openai",
            "--backend", "oss",
            "--mem0-host", "http://localhost:8000",
            "--chat-sizes", "100K",
            "--conversations", "0",
            "--question-types", "abstention",
            "--top-k", "20",
            "--top-k-cutoffs", "10",
            "--max-workers", "1",
            "--rpm", "4000"
        )
    }
)

$failures = @()
$startedAt = Get-Date

foreach ($job in $jobs) {
    $elapsed = ((Get-Date) - $startedAt).TotalMinutes
    if ($elapsed -gt $TimeoutMinutes) {
        throw "Benchmark smoke gate exceeded timeout before $($job.Name)"
    }

    $outLog = Join-Path $gateDir ("{0}.out.log" -f $job.Name)
    $errLog = Join-Path $gateDir ("{0}.err.log" -f $job.Name)
    Write-Output ("[{0}] Starting {1}" -f (Get-Date -Format "s"), $job.Name)
    $argumentList = @($runner) + @($job.Args)
    $oldErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $python @argumentList 1> $outLog 2> $errLog
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $oldErrorActionPreference
    }
    Write-Output ("[{0}] {1} exited with code {2}" -f (Get-Date -Format "s"), $job.Name, $exitCode)
    if ($exitCode -ne 0) {
        $failures += $job.Name
        Get-Content -LiteralPath $errLog -Tail 80 | ForEach-Object {
            Write-Output ("[{0} stderr] {1}" -f $job.Name, $_)
        }
        break
    }
}

$passed = $failures.Count -eq 0
$meta = [ordered]@{
    timestamp = $stamp
    git_sha = $gitSha
    worktree = $dirtyFlag
    smoke_only = $true
    public_performance_evidence = $false
    note = "Harness smoke only. This is not a leaderboard run and must not be used for benchmark claims."
    timeout_minutes = $TimeoutMinutes
    gate_dir = $gateDir
    gate_pass = $passed
    failures = @($failures)
}
Write-JsonUtf8NoBom -Data $meta -Path $metaPath -Depth 4

if (-not $passed) {
    Write-Error "BENCHMARK SMOKE GATE: FAIL - $($failures -join ', ')"
    exit 1
}

Write-Output "BENCHMARK SMOKE GATE: PASS"
Write-Output "gate dir: $gateDir"
Write-Output "metadata: $metaPath"
Write-Output "NOTE: smoke_only=true; not public performance evidence"
