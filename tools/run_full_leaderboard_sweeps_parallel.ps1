param(
    [int]$MaxParallel = 2,
    [int]$LaneTimeoutMinutes = 240,
    [int]$IdleTimeoutMinutes = 20
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
    $projectSuffix = "public_parallel_" + (Get-Date -Format "yyyyMMdd_HHmmss")
    $env:MAPU_BENCH_PROJECT_SUFFIX = $projectSuffix
}
Write-Output ("[{0}] Public benchmark project suffix: {1}" -f (Get-Date -Format "s"), $projectSuffix)
Write-Output ("[{0}] Max parallel benchmark jobs: {1}" -f (Get-Date -Format "s"), $MaxParallel)
Write-Output ("[{0}] Lane timeout minutes: {1}" -f (Get-Date -Format "s"), $LaneTimeoutMinutes)
Write-Output ("[{0}] Idle timeout minutes: {1}" -f (Get-Date -Format "s"), $IdleTimeoutMinutes)

$logDir = Join-Path $repoRoot "logs\benchmarks\parallel_$projectSuffix"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

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
            Write-Output ("[{0}] {1} exited with code {2}" -f (Get-Date -Format "s"), $entry.Name, $exitCodeLabel)
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
                Write-Output ("[{0}] {1} exceeded lane timeout after {2:N1} minutes" -f (Get-Date -Format "s"), $entry.Name, $elapsedMinutes)
                $failures += $entry
                Stop-RunningBenchmarks -Entries $running
                break
            }
            if ($idleMinutes -gt $IdleTimeoutMinutes) {
                Write-Output ("[{0}] {1} exceeded idle timeout after {2:N1} minutes without CPU or log progress" -f (Get-Date -Format "s"), $entry.Name, $idleMinutes)
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
