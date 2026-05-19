param(
    [int]$MaxParallel = 2,
    [int]$LaneTimeoutMinutes = 240,
    [int]$IdleTimeoutMinutes = 20,
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

if ($MaxParallel -lt 1) {
    throw "MaxParallel must be >= 1"
}
if ($LaneTimeoutMinutes -lt 1) {
    throw "LaneTimeoutMinutes must be >= 1"
}
if ($IdleTimeoutMinutes -lt 1) {
    throw "IdleTimeoutMinutes must be >= 1"
}
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
    $projectSuffix = "public_parallel_" + (Get-Date -Format "yyyyMMdd_HHmmss")
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
Write-Output ("[{0}] Max parallel benchmark jobs: {1}" -f (Get-Date -Format "s"), $MaxParallel)
Write-Output ("[{0}] Lane timeout minutes: {1}" -f (Get-Date -Format "s"), $LaneTimeoutMinutes)
Write-Output ("[{0}] Idle timeout minutes: {1}" -f (Get-Date -Format "s"), $IdleTimeoutMinutes)
Write-Output ("[{0}] Benchmark mem0 host argument: {1}" -f (Get-Date -Format "s"), $BenchmarkMem0HostArg)
Write-Output ("[{0}] Resume existing benchmark checkpoints: {1}" -f (Get-Date -Format "s"), $Resume.IsPresent)

$logDir = Join-Path $repoRoot "logs\benchmarks\parallel_$projectSuffix"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

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

$queue = [System.Collections.Queue]::new()
foreach ($job in $jobs) {
    $queue.Enqueue($job)
}

$running = @()
$failures = @()

function Get-FileLength {
    param([string]$Path)
    if (Test-Path -LiteralPath $Path) {
        return (Get-Item -LiteralPath $Path).Length
    }
    return 0
}

function Get-ProcessCpuSeconds {
    param([System.Diagnostics.Process]$Process)
    $cpuSeconds = 0.0
    try {
        $Process.Refresh()
        $cpuSeconds += $Process.TotalProcessorTime.TotalSeconds
    }
    catch {
        return $cpuSeconds
    }
    $children = Get-CimInstance Win32_Process -Filter ("ParentProcessId={0}" -f $Process.Id)
    foreach ($child in $children) {
        try {
            $childProcess = Get-Process -Id $child.ProcessId -ErrorAction Stop
            $cpuSeconds += $childProcess.TotalProcessorTime.TotalSeconds
        }
        catch {
            # Child may have exited between the process-tree query and lookup.
        }
    }
    return $cpuSeconds
}

function Write-LaneMetadata {
    param(
        [pscustomobject]$Entry,
        [datetime]$FinishedAt,
        [object]$ExitCode,
        [string]$FailureReason = ""
    )

    $meta = [ordered]@{
        name = $Entry.Name
        args = @($Entry.Args)
        stdout_log = $Entry.StdoutLog
        stderr_log = $Entry.StderrLog
        started_at = $Entry.StartedAt.ToString("o")
        finished_at = $FinishedAt.ToString("o")
        elapsed_seconds = [math]::Round(($FinishedAt - $Entry.StartedAt).TotalSeconds, 3)
        exit_code = $ExitCode
        failure_reason = $FailureReason
        last_progress_at = $Entry.LastProgressAt.ToString("o")
        last_cpu_seconds = [math]::Round($Entry.LastCpuSeconds, 3)
        stdout_bytes = Get-FileLength -Path $Entry.StdoutLog
        stderr_bytes = Get-FileLength -Path $Entry.StderrLog
    }
    $metaPath = Join-Path $logDir ("{0}.meta.json" -f $Entry.Name)
    Write-JsonUtf8NoBom -Data $meta -Path $metaPath -Depth 6
    Write-Output ("[{0}] {1} metadata: {2}" -f (Get-Date -Format "s"), $Entry.Name, $metaPath)
}

function Stop-RunningBenchmarks {
    param([array]$Entries)

    foreach ($entry in $Entries) {
        try {
            $entry.Process.Refresh()
            if (-not $entry.Process.HasExited) {
                Write-Output ("[{0}] Stopping {1} PID={2}" -f (Get-Date -Format "s"), $entry.Name, $entry.Process.Id)
                Get-CimInstance Win32_Process -Filter ("ParentProcessId={0}" -f $entry.Process.Id) |
                    ForEach-Object {
                        $childPid = $_.ProcessId
                        try {
                            Stop-Process -Id $childPid -Force -ErrorAction Stop
                        }
                        catch {
                            Write-Output ("[{0}] Failed to stop child PID={1}: {2}" -f (Get-Date -Format "s"), $childPid, $_.Exception.Message)
                        }
                    }
                $entry.Process.Kill()
                $entry.Process.WaitForExit(30000) | Out-Null
            }
        }
        catch {
            Write-Output ("[{0}] Failed to stop {1}: {2}" -f (Get-Date -Format "s"), $entry.Name, $_.Exception.Message)
        }
    }
}

function Start-BenchmarkProcess {
    param([hashtable]$Job)

    $stdoutLog = Join-Path $logDir ("{0}.out.log" -f $Job.Name)
    $stderrLog = Join-Path $logDir ("{0}.err.log" -f $Job.Name)
    $process = Start-Process `
        -FilePath $python `
        -ArgumentList $Job.Args `
        -WorkingDirectory $repoRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutLog `
        -RedirectStandardError $stderrLog `
        -PassThru

    [Console]::Out.WriteLine(("[{0}] Started {1} PID={2}" -f (Get-Date -Format "s"), $Job.Name, $process.Id))
    return [pscustomobject]@{
        Name = $Job.Name
        Args = @($Job.Args)
        Process = $process
        StdoutLog = $stdoutLog
        StderrLog = $stderrLog
        StartedAt = Get-Date
        LastProgressAt = Get-Date
        LastCpuSeconds = 0.0
        LastStdoutLength = Get-FileLength -Path $stdoutLog
        LastStderrLength = Get-FileLength -Path $stderrLog
    }
}

while (($queue.Count -gt 0) -or ($running.Count -gt 0)) {
    while (($queue.Count -gt 0) -and ($running.Count -lt $MaxParallel)) {
        $running += Start-BenchmarkProcess -Job $queue.Dequeue()
    }

    Start-Sleep -Seconds 10
    $stillRunning = @()
    foreach ($entry in $running) {
        $entry.Process.Refresh()
        if ($entry.Process.HasExited) {
            $entry.Process.WaitForExit()
            $exitCode = $entry.Process.ExitCode
            $exitCodeLabel = if ($null -eq $exitCode) { "<null>" } else { [string]$exitCode }
            $failureReason = if (($null -eq $exitCode) -or ($exitCode -ne 0)) {
                "exited with code $exitCodeLabel"
            }
            else {
                ""
            }
            Write-LaneMetadata -Entry $entry -FinishedAt (Get-Date) -ExitCode $exitCode -FailureReason $failureReason
            Write-Output ("[{0}] {1} exited with code {2}; stdout={3}; stderr={4}" -f (Get-Date -Format "s"), $entry.Name, $exitCodeLabel, $entry.StdoutLog, $entry.StderrLog)
            if (($null -eq $exitCode) -or ($exitCode -ne 0)) {
                $failures += $entry
                if (Test-Path -LiteralPath $entry.StderrLog) {
                    Get-Content -LiteralPath $entry.StderrLog -Tail 80 | ForEach-Object {
                        Write-Output ("[{0} stderr] {1}" -f $entry.Name, $_)
                    }
                }
                Stop-RunningBenchmarks -Entries $stillRunning
                Stop-RunningBenchmarks -Entries ($running | Where-Object { $_.Name -ne $entry.Name })
                break
            }
        }
        else {
            $now = Get-Date
            $cpuSeconds = Get-ProcessCpuSeconds -Process $entry.Process
            $stdoutLength = Get-FileLength -Path $entry.StdoutLog
            $stderrLength = Get-FileLength -Path $entry.StderrLog
            $hasProgress = (
                ($cpuSeconds -gt ($entry.LastCpuSeconds + 0.1)) -or
                ($stdoutLength -ne $entry.LastStdoutLength) -or
                ($stderrLength -ne $entry.LastStderrLength)
            )
            if ($hasProgress) {
                $entry.LastProgressAt = $now
                $entry.LastCpuSeconds = $cpuSeconds
                $entry.LastStdoutLength = $stdoutLength
                $entry.LastStderrLength = $stderrLength
            }

            $elapsedMinutes = ($now - $entry.StartedAt).TotalMinutes
            $idleMinutes = ($now - $entry.LastProgressAt).TotalMinutes
            if ($elapsedMinutes -gt $LaneTimeoutMinutes) {
                $reason = "exceeded lane timeout after {0:N1} minutes" -f $elapsedMinutes
                Write-LaneMetadata -Entry $entry -FinishedAt $now -ExitCode $null -FailureReason $reason
                Write-Output ("[{0}] {1} {2}; stdout={3}; stderr={4}" -f (Get-Date -Format "s"), $entry.Name, $reason, $entry.StdoutLog, $entry.StderrLog)
                $failures += $entry
                Stop-RunningBenchmarks -Entries $running
                break
            }
            if ($idleMinutes -gt $IdleTimeoutMinutes) {
                $reason = "exceeded idle timeout after {0:N1} minutes without CPU or log progress" -f $idleMinutes
                Write-LaneMetadata -Entry $entry -FinishedAt $now -ExitCode $null -FailureReason $reason
                Write-Output ("[{0}] {1} {2}; stdout={3}; stderr={4}" -f (Get-Date -Format "s"), $entry.Name, $reason, $entry.StdoutLog, $entry.StderrLog)
                $failures += $entry
                Stop-RunningBenchmarks -Entries $running
                break
            }
            $stillRunning += $entry
        }
    }
    if ($failures.Count -gt 0) {
        break
    }
    $running = $stillRunning
}

if ($failures.Count -gt 0) {
    $names = ($failures | ForEach-Object { $_.Name }) -join ", "
    throw "Parallel leaderboard sweep failed: $names"
}

Write-Output ("[{0}] All parallel benchmark sweeps completed." -f (Get-Date -Format "s"))
