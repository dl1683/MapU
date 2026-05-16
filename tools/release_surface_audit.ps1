param(
    [switch]$SkipFreshInstall,
    [switch]$KeepTemp,
    [string]$Python = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location -LiteralPath $repoRoot

$failures = New-Object System.Collections.Generic.List[string]

function Add-Failure {
    param([string]$Message)
    $script:failures.Add($Message)
    Write-Output ("FAIL: {0}" -f $Message)
}

function Add-Pass {
    param([string]$Message)
    Write-Output ("PASS: {0}" -f $Message)
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

Write-Output "MapU release surface audit"
Write-Output ("repo: {0}" -f $repoRoot)
Write-Output ("sha: {0}" -f (& git rev-parse HEAD))

Invoke-Checked "git worktree is clean" {
    $dirty = & git status --porcelain
    if ($dirty) {
        throw "worktree has uncommitted changes"
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

Invoke-Checked "docker command is available for compose verification" {
    $docker = Get-Command docker -ErrorAction Stop
    & $docker.Source --version | Out-Null
    & $docker.Source compose version | Out-Null
}

if (-not $SkipFreshInstall) {
    Invoke-Checked "fresh clone installs and exposes public Python/CLI/MCP surfaces" {
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

        $checkout = Join-Path $auditRoot "checkout"
        $repoUri = "file:///" + ($repoRoot -replace "\\", "/")
        & git clone --depth 1 $repoUri $checkout | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "git clone failed"
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
        & $mapu mcp --help | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "installed CLI help check failed"
        }
        & $python (Join-Path $repoRoot "tools\mcp_stdio_smoke.py") --command $mapu --arg mcp | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "installed MCP stdio smoke failed"
        }

        if (-not $KeepTemp) {
            Remove-Item -LiteralPath $auditRoot -Recurse -Force
        }
    }
}
else {
    Write-Output "SKIP: fresh clone install audit"
}

if ($failures.Count -gt 0) {
    Write-Output ""
    Write-Output ("Release surface audit failed with {0} issue(s)." -f $failures.Count)
    exit 1
}

Write-Output ""
Write-Output "Release surface audit passed."
