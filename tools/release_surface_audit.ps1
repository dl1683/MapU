param(
    [switch]$SkipFreshInstall,
    [switch]$SkipDocker,
    [switch]$AllowDirtyWorktree,
    [switch]$InstallFromWorkingTree,
    [switch]$RunCliE2E,
    [switch]$RunMcpE2E,
    [switch]$KeepTemp,
    [string]$Python = "",
    [string]$OutputJson = "",
    [int]$CliE2ETimeoutSeconds = 120,
    [int]$McpE2ETimeoutSeconds = 120,
    [int]$McpE2EToolTimeoutSeconds = 60
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location -LiteralPath $repoRoot

$failures = New-Object System.Collections.Generic.List[string]
$passes = New-Object System.Collections.Generic.List[string]
$skips = New-Object System.Collections.Generic.List[string]
$evidenceReports = New-Object System.Collections.Generic.List[object]
$installedDoctorEvidence = $null

function Add-Failure {
    param([string]$Message)
    $script:failures.Add($Message)
    Write-Output ("FAIL: {0}" -f $Message)
}

function Add-Pass {
    param([string]$Message)
    $script:passes.Add($Message)
    Write-Output ("PASS: {0}" -f $Message)
}

function Add-Skip {
    param([string]$Message)
    $script:skips.Add($Message)
    Write-Output ("SKIP: {0}" -f $Message)
}

function Invoke-Checked {
    param(
        [string]$Description,
        [scriptblock]$Script
    )
    try {
        & $Script
        Add-Pass $Description
    }
    catch {
        Add-Failure ("{0}: {1}" -f $Description, $_.Exception.Message)
    }
}

function Get-PythonCommand {
    if (-not [string]::IsNullOrWhiteSpace($Python)) {
        return @{
            Executable = $Python
            Args = @()
            Label = $Python
        }
    }

    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        return @{
            Executable = $pyLauncher.Source
            Args = @("-3.13")
            Label = "py -3.13"
        }
    }

    $pythonExe = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonExe) {
        return @{
            Executable = $pythonExe.Source
            Args = @()
            Label = "python"
        }
    }

    throw "no Python launcher found; install Python 3.12-3.14 or pass -Python <path>"
}

function Assert-SmokeEvidenceReport {
    param(
        [string]$Path,
        [string]$Kind
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "$Kind smoke evidence file not found: $Path"
    }

    $report = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    $properties = @($report.PSObject.Properties.Name)
    foreach ($required in @("status", "command", "mapu_version", "git_sha", "corpus_id", "required_checks", "failed_checks")) {
        if ($properties -notcontains $required) {
            throw "$Kind smoke evidence missing '$required'"
        }
    }
    if ($report.status -ne "ok") {
        throw "$Kind smoke evidence status is '$($report.status)'"
    }
    if ([string]::IsNullOrWhiteSpace([string]$report.mapu_version)) {
        throw "$Kind smoke evidence missing mapu_version value"
    }
    if ([string]::IsNullOrWhiteSpace([string]$report.git_sha)) {
        throw "$Kind smoke evidence missing git_sha value"
    }
    if ($report.git_sha -ne $auditSha) {
        throw "$Kind smoke evidence git_sha '$($report.git_sha)' does not match audit sha '$auditSha'"
    }
    if ([string]::IsNullOrWhiteSpace([string]$report.corpus_id)) {
        throw "$Kind smoke evidence missing corpus_id value"
    }
    if (@($report.failed_checks).Count -ne 0) {
        throw "$Kind smoke evidence has failed checks: $($report.failed_checks -join ', ')"
    }
    foreach ($check in $report.required_checks.PSObject.Properties) {
        if (-not [bool]$check.Value) {
            throw "$Kind smoke evidence required check failed: $($check.Name)"
        }
    }

    $requiredChecks = [ordered]@{}
    foreach ($check in $report.required_checks.PSObject.Properties) {
        $requiredChecks[$check.Name] = [bool]$check.Value
    }
    $toolNames = @()
    if ($properties -contains "tools") {
        $toolNames = @($report.tools | ForEach-Object { [string]$_ })
    }
    $missingRequiredTools = @()
    if ($properties -contains "missing_required_tools") {
        $missingRequiredTools = @($report.missing_required_tools | ForEach-Object { [string]$_ })
    }
    $commandLine = New-Object System.Collections.Generic.List[string]
    foreach ($part in @($report.command)) {
        if (-not [string]::IsNullOrWhiteSpace([string]$part)) {
            $commandLine.Add([string]$part)
        }
    }
    if ($properties -contains "args") {
        foreach ($part in @($report.args)) {
            if (-not [string]::IsNullOrWhiteSpace([string]$part)) {
                $commandLine.Add([string]$part)
            }
        }
    }

    $script:evidenceReports.Add([ordered]@{
        kind = $Kind
        path = $Path
        status = [string]$report.status
        command_line = [string[]]$commandLine.ToArray()
        command = @($report.command)
        corpus_id = [string]$report.corpus_id
        mapu_version = [string]$report.mapu_version
        git_sha = [string]$report.git_sha
        required_checks = $requiredChecks
        tool_count = if ($properties -contains "tool_count") { [int]$report.tool_count } else { $null }
        required_tools_present = if ($properties -contains "required_tools_present") { [bool]$report.required_tools_present } else { $null }
        missing_required_tools = [string[]]$missingRequiredTools
        tools = [string[]]$toolNames
    })
}

function Get-SmokeEvidenceArray {
    $items = @($script:evidenceReports.ToArray())
    return ,$items
}

function Write-JsonUtf8NoBom {
    param(
        [object]$Data,
        [string]$Path
    )

    $absolutePath = [System.IO.Path]::GetFullPath($Path)
    $parent = [System.IO.Path]::GetDirectoryName($absolutePath)
    if (-not [string]::IsNullOrWhiteSpace($parent)) {
        [System.IO.Directory]::CreateDirectory($parent) | Out-Null
    }
    $json = $Data | ConvertTo-Json -Depth 5
    $encoding = New-Object System.Text.UTF8Encoding -ArgumentList $false
    [System.IO.File]::WriteAllText($absolutePath, ($json + [Environment]::NewLine), $encoding)
}

function Get-WorktreeFingerprint {
    $pythonCommand = Get-PythonCommand
    $fingerprintJson = & $pythonCommand.Executable @($pythonCommand.Args) tools/worktree_fingerprint.py --repo-root $repoRoot --json
    if ($LASTEXITCODE -ne 0) {
        throw "worktree fingerprint failed with $($pythonCommand.Label): $fingerprintJson"
    }
    $fingerprint = $fingerprintJson | ConvertFrom-Json
    if ($fingerprint.status -ne "ok") {
        throw "worktree fingerprint failed: $fingerprintJson"
    }
    return [ordered]@{
        status_porcelain = @($fingerprint.worktree_status_porcelain)
        dirty_path_count = [int]$fingerprint.worktree_dirty_path_count
        sha256 = [string]$fingerprint.worktree_fingerprint_sha256
    }
}

Write-Output "MapU release surface audit"
Write-Output ("repo: {0}" -f $repoRoot)
$auditSha = (& git rev-parse HEAD)
Write-Output ("sha: {0}" -f $auditSha)
$worktreeFingerprint = Get-WorktreeFingerprint

if ($AllowDirtyWorktree) {
    $dirty = & git status --porcelain
    if ($dirty) {
        Add-Skip "git worktree is clean (-AllowDirtyWorktree set; local development audit only)"
    }
    else {
        Add-Pass "git worktree is clean"
    }
}
else {
    Invoke-Checked "git worktree is clean" {
        $dirty = & git status --porcelain
        if ($dirty) {
            throw "worktree has uncommitted changes"
        }
    }
}

Invoke-Checked "tracked files are under 1 MiB" {
    $large = @(
        git ls-files | ForEach-Object {
            $item = Get-Item -LiteralPath $_ -ErrorAction SilentlyContinue
            if ($item -and $item.Length -gt 1048576) {
                "{0} ({1:N2} MiB)" -f $_, ($item.Length / 1MB)
            }
        }
    )
    if ($large.Count -gt 0) {
        throw ($large -join "; ")
    }
}

Invoke-Checked "license file matches package metadata" {
    $licensePath = Join-Path $repoRoot "LICENSE"
    $projectPath = Join-Path $repoRoot "pyproject.toml"
    if (-not (Test-Path -LiteralPath $licensePath)) {
        throw "missing LICENSE file"
    }
    if (-not (Test-Path -LiteralPath $projectPath)) {
        throw "missing pyproject.toml"
    }
    $license = Get-Content -LiteralPath $licensePath -Raw
    $project = Get-Content -LiteralPath $projectPath -Raw
    if (-not $project.Contains('license = "AGPL-3.0-only"')) {
        throw "pyproject.toml does not declare AGPL-3.0-only"
    }
    if (-not $license.Contains("SPDX-License-Identifier: AGPL-3.0-only")) {
        throw "LICENSE file does not contain the AGPL-3.0-only SPDX identifier"
    }
}

Invoke-Checked "tracked markdown local links resolve" {
    $markdownFiles = @(git ls-files "*.md")
    $missing = New-Object System.Collections.Generic.List[string]
    $linkPattern = [regex]'\[[^\]]+\]\(([^)]+)\)'

    foreach ($file in $markdownFiles) {
        $content = Get-Content -LiteralPath $file -Raw
        foreach ($match in $linkPattern.Matches($content)) {
            $target = $match.Groups[1].Value.Trim()
            if (
                $target.StartsWith("http://") -or
                $target.StartsWith("https://") -or
                $target.StartsWith("mailto:") -or
                $target.StartsWith("#")
            ) {
                continue
            }
            $targetPath = ($target -split "#", 2)[0]
            if ([string]::IsNullOrWhiteSpace($targetPath)) {
                continue
            }
            $normalized = $targetPath -replace "/", [System.IO.Path]::DirectorySeparatorChar
            $baseDir = Split-Path -Parent $file
            if ([string]::IsNullOrWhiteSpace($baseDir)) {
                $baseDir = "."
            }
            $candidate = Join-Path $baseDir $normalized
            if (-not (Test-Path -LiteralPath $candidate)) {
                $missing.Add(("{0} -> {1}" -f $file, $target))
            }
        }
    }

    if ($missing.Count -gt 0) {
        throw ($missing -join "; ")
    }
}

Invoke-Checked "tracked files contain no obvious private secret material" {
    $patterns = @(
        "sk-[A-Za-z0-9_-]{20,}",
        "BEGIN (RSA|OPENSSH|EC|DSA) PRIVATE KEY"
    )
    $hits = New-Object System.Collections.Generic.List[string]
    foreach ($pattern in $patterns) {
        $result = & rg -n --hidden `
            --glob "!.git" `
            --glob "!logs/**" `
            --glob "!results/**" `
            --glob "!datasets/**" `
            --glob "!.tmp/**" `
            --glob "!.venv/**" `
            --glob "!.claude/**" `
            --glob "!.process/**" `
            $pattern .
        if ($LASTEXITCODE -eq 0) {
            foreach ($line in $result) {
                $hits.Add($line)
            }
        }
        elseif ($LASTEXITCODE -ne 1) {
            throw "rg failed for pattern: $pattern"
        }
    }
    if ($hits.Count -gt 0) {
        throw ($hits -join "; ")
    }
}

Invoke-Checked "dummy benchmark API keys are explicitly dummy only" {
    $result = & rg -n --hidden `
        --glob "!.git" `
        --glob "!logs/**" `
        --glob "!results/**" `
        --glob "!datasets/**" `
        --glob "!.tmp/**" `
        --glob "!.venv/**" `
        --glob "!.claude/**" `
        --glob "!.process/**" `
        "OPENAI_API_KEY|ANTHROPIC_API_KEY" .
    if ($LASTEXITCODE -eq 1) {
        return
    }
    if ($LASTEXITCODE -ne 0) {
        throw "rg failed while scanning API key names"
    }
    foreach ($line in $result) {
        if ($line -notmatch "dummy|os\.getenv|GLOBAL_MEMORY_BENCHMARK_STATUS|release_surface_audit\.ps1") {
            throw $line
        }
    }
}

Invoke-Checked "benchmark-specific code is isolated from general runtime" {
    $pythonCommand = Get-PythonCommand
    & $pythonCommand.Executable @($pythonCommand.Args) tools/verify_benchmark_isolation.py | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "benchmark isolation verifier failed"
    }
}

Invoke-Checked "docker compose file matches documented local infra" {
    $composePath = Join-Path $repoRoot "docker-compose.yml"
    $envExamplePath = Join-Path $repoRoot ".env.example"
    if (-not (Test-Path -LiteralPath $composePath)) {
        throw "missing docker-compose.yml"
    }
    if (-not (Test-Path -LiteralPath $envExamplePath)) {
        throw "missing .env.example"
    }

    $compose = Get-Content -LiteralPath $composePath -Raw
    $envExample = Get-Content -LiteralPath $envExamplePath -Raw
    foreach ($required in @(
            "postgres:",
            "image: pgvector/pgvector:pg17",
            "POSTGRES_USER: mapu",
            "POSTGRES_PASSWORD: mapu",
            "POSTGRES_DB: mapu",
            '"5432:5432"',
            "redis:",
            "image: redis:7-alpine",
            '"6379:6379"'
        )) {
        if (-not $compose.Contains($required)) {
            throw "docker-compose.yml missing expected local infra entry: $required"
        }
    }
    if (-not $envExample.Contains("MAPU_DB_URL=postgresql+asyncpg://mapu:mapu@localhost:5432/mapu")) {
        throw ".env.example MAPU_DB_URL does not match docker-compose.yml postgres service"
    }
}

if ($SkipDocker) {
    Add-Skip "docker command is available for compose verification (-SkipDocker set; local development audit only)"
}
else {
    Invoke-Checked "docker command is available for compose verification" {
        $docker = Get-Command docker -ErrorAction Stop
        & $docker.Source --version | Out-Null
        & $docker.Source compose version | Out-Null
    }
}

if ($RunCliE2E) {
    Invoke-Checked "DB-backed CLI continuity loop works end-to-end" {
        $uv = Get-Command uv -ErrorAction Stop
        & $uv.Source run python tools/cli_e2e_smoke.py `
            --command uv `
            --arg run `
            --arg mapu `
            --timeout $CliE2ETimeoutSeconds `
            --json | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "CLI e2e smoke failed"
        }
        Assert-SmokeEvidenceReport `
            -Path (Join-Path $repoRoot "logs\cli_e2e_smoke_last.json") `
            -Kind "CLI e2e"
    }
}
else {
    Add-Skip "DB-backed CLI e2e smoke (-RunCliE2E not set)"
}

if ($RunMcpE2E) {
    Invoke-Checked "DB-backed MCP stdio loop works end-to-end" {
        $uv = Get-Command uv -ErrorAction Stop
        & $uv.Source run python tools/mcp_stdio_smoke.py `
            --command uv `
            --arg run `
            --arg mapu `
            --arg mcp `
            --timeout $McpE2ETimeoutSeconds `
            --tool-timeout $McpE2EToolTimeoutSeconds `
            --json | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "MCP e2e smoke failed"
        }
        Assert-SmokeEvidenceReport `
            -Path (Join-Path $repoRoot "logs\mcp_stdio_smoke_last.json") `
            -Kind "MCP stdio e2e"
    }
}
else {
    Add-Skip "DB-backed MCP stdio e2e smoke (-RunMcpE2E not set)"
}

if (-not $SkipFreshInstall) {
    $installCheckName = if ($InstallFromWorkingTree) {
        "working tree installs and exposes Python/CLI/MCP surfaces"
    }
    else {
        "fresh clone installs and exposes public Python/CLI/MCP surfaces"
    }
    Invoke-Checked $installCheckName {
        $auditRoot = Join-Path $repoRoot ".tmp\release-surface-audit"
        if (Test-Path -LiteralPath $auditRoot) {
            $resolved = Resolve-Path -LiteralPath $auditRoot
            $tmpRoot = (Resolve-Path -LiteralPath (Join-Path $repoRoot ".tmp")).Path
            if (-not $resolved.Path.StartsWith($tmpRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "refusing to delete outside .tmp: $($resolved.Path)"
            }
            Remove-Item -LiteralPath $resolved.Path -Recurse -Force
        }
        New-Item -ItemType Directory -Force -Path $auditRoot | Out-Null

        if ($InstallFromWorkingTree) {
            $checkout = $repoRoot
            Write-Output "Using current working tree as install source (-InstallFromWorkingTree set; local development audit only)"
        }
        else {
            $checkout = Join-Path $auditRoot "checkout"
            $repoUri = "file:///" + ($repoRoot -replace "\\", "/")
            & git clone --depth 1 $repoUri $checkout | Out-Null
            if ($LASTEXITCODE -ne 0) {
                throw "git clone failed"
            }
        }

        $pythonCommand = Get-PythonCommand
        Write-Output ("Using Python launcher: {0}" -f $pythonCommand.Label)

        $venv = Join-Path $auditRoot "venv"
        & $pythonCommand.Executable @($pythonCommand.Args) -m venv $venv
        if ($LASTEXITCODE -ne 0) {
            throw "venv creation failed with $($pythonCommand.Label)"
        }

        $python = Join-Path $venv "Scripts\python.exe"
        if (-not (Test-Path -LiteralPath $python)) {
            $python = Join-Path $venv "bin/python"
        }
        if (-not (Test-Path -LiteralPath $python)) {
            throw "venv Python executable not found"
        }
        & $python -m pip install $checkout | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "pip install failed"
        }
        $mapu = Join-Path $venv "Scripts\mapu.exe"
        if (-not (Test-Path -LiteralPath $mapu)) {
            $mapu = Join-Path $venv "bin/mapu"
        }
        if (-not (Test-Path -LiteralPath $mapu)) {
            throw "installed mapu console script not found"
        }
        & $python -c "import mapu, mapu.cli, mapu.api.app, mapu.mcp.server; from importlib.metadata import metadata; m=metadata('mapu'); assert m['License-Expression']=='AGPL-3.0-only'; assert m['Requires-Python']=='<3.15,>=3.12'; print(mapu.__file__)"
        if ($LASTEXITCODE -ne 0) {
            throw "installed import/metadata check failed"
        }
        & $mapu --help | Out-Null
        & $mapu corpus --help | Out-Null
        & $mapu serve --help | Out-Null
        & $mapu doctor --help | Out-Null
        & $mapu mcp --help | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "installed CLI help check failed"
        }
        $installedDoctorOut = Join-Path $auditRoot "installed_mapu_doctor.json"
        & $mapu doctor --json > $installedDoctorOut
        if ($LASTEXITCODE -ne 0) {
            throw "installed doctor check failed"
        }
        $script:installedDoctorEvidence = Get-Content -LiteralPath $installedDoctorOut -Raw |
            ConvertFrom-Json
        if ($script:installedDoctorEvidence.status -ne "ok") {
            throw "installed doctor status is not ok"
        }
        $installedMcpSmokeOut = Join-Path $auditRoot "installed_mcp_stdio_smoke_last.json"
        & $python (Join-Path $repoRoot "tools\mcp_stdio_smoke.py") `
            --command $mapu `
            --arg mcp `
            --list-only `
            --out $installedMcpSmokeOut | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "installed MCP stdio smoke failed"
        }

        if (-not $KeepTemp) {
            Remove-Item -LiteralPath $auditRoot -Recurse -Force
        }
    }
}
else {
    Add-Skip "fresh clone install audit"
}

if ($failures.Count -gt 0) {
    if (-not [string]::IsNullOrWhiteSpace($OutputJson)) {
        $releaseReadyEvidence = $false
        $summary = [ordered]@{
            repo = $repoRoot
            sha = $auditSha
            worktree_status_porcelain = @($worktreeFingerprint.status_porcelain)
            worktree_dirty_path_count = [int]$worktreeFingerprint.dirty_path_count
            worktree_fingerprint_sha256 = [string]$worktreeFingerprint.sha256
            passed = $false
            release_ready_evidence = $releaseReadyEvidence
            evidence_scope = "failed"
            skip_fresh_install = [bool]$SkipFreshInstall
            skip_docker = [bool]$SkipDocker
            allow_dirty_worktree = [bool]$AllowDirtyWorktree
            install_from_working_tree = [bool]$InstallFromWorkingTree
            run_cli_e2e = [bool]$RunCliE2E
            run_mcp_e2e = [bool]$RunMcpE2E
            installed_doctor_evidence = $installedDoctorEvidence
            smoke_evidence = Get-SmokeEvidenceArray
            checks_passed = @($passes)
            checks_skipped = @($skips)
            checks_failed = @($failures)
        }
        Write-JsonUtf8NoBom -Data $summary -Path $OutputJson
    }
    Write-Output ""
    Write-Output ("Release surface audit failed with {0} issue(s)." -f $failures.Count)
    exit 1
}

if (-not [string]::IsNullOrWhiteSpace($OutputJson)) {
    $releaseReadyEvidence = (
        (-not [bool]$SkipFreshInstall) -and
        (-not [bool]$SkipDocker) -and
        (-not [bool]$AllowDirtyWorktree) -and
        (-not [bool]$InstallFromWorkingTree) -and
        ($skips.Count -eq 0)
    )
    $evidenceScope = if ($releaseReadyEvidence) { "release" } else { "scoped" }
    $summary = [ordered]@{
        repo = $repoRoot
        sha = $auditSha
        worktree_status_porcelain = @($worktreeFingerprint.status_porcelain)
        worktree_dirty_path_count = [int]$worktreeFingerprint.dirty_path_count
        worktree_fingerprint_sha256 = [string]$worktreeFingerprint.sha256
        passed = $true
        release_ready_evidence = $releaseReadyEvidence
        evidence_scope = $evidenceScope
        skip_fresh_install = [bool]$SkipFreshInstall
        skip_docker = [bool]$SkipDocker
        allow_dirty_worktree = [bool]$AllowDirtyWorktree
        install_from_working_tree = [bool]$InstallFromWorkingTree
        run_cli_e2e = [bool]$RunCliE2E
        run_mcp_e2e = [bool]$RunMcpE2E
        installed_doctor_evidence = $installedDoctorEvidence
        smoke_evidence = Get-SmokeEvidenceArray
        checks_passed = @($passes)
        checks_skipped = @($skips)
        checks_failed = @()
    }
    Write-JsonUtf8NoBom -Data $summary -Path $OutputJson
}

Write-Output ""
Write-Output "Release surface audit passed."
