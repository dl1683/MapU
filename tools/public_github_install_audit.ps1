param(
    [string]$RepoUrl = "https://github.com/dl1683/MapU.git",
    [string]$Ref = "main",
    [switch]$KeepTemp,
    [string]$Python = "",
    [string]$OutputJson = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location -LiteralPath $repoRoot

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

function Write-Summary {
    param(
        [bool]$Passed,
        [string]$Sha,
        [string[]]$ChecksPassed,
        [string[]]$ChecksFailed
    )
    if ([string]::IsNullOrWhiteSpace($OutputJson)) {
        return
    }
    $summary = [ordered]@{
        repo_url = $RepoUrl
        ref = $Ref
        sha = $Sha
        passed = $Passed
        checks_passed = $ChecksPassed
        checks_failed = $ChecksFailed
    }
    ($summary | ConvertTo-Json -Depth 5) | Set-Content -LiteralPath $OutputJson -Encoding UTF8
}

$checksPassed = New-Object System.Collections.Generic.List[string]
$checksFailed = New-Object System.Collections.Generic.List[string]
$remoteSha = "unknown"

Write-Output "MapU public GitHub install audit"
Write-Output ("repo url: {0}" -f $RepoUrl)
Write-Output ("ref: {0}" -f $Ref)

try {
    $auditRoot = Join-Path $repoRoot ".tmp\public-github-install-audit"
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
    & git clone --depth 1 --branch $Ref $RepoUrl $checkout | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "git clone failed"
    }
    $checksPassed.Add("public git clone completed")

    Push-Location -LiteralPath $checkout
    try {
        $remoteSha = (& git rev-parse HEAD)
    }
    finally {
        Pop-Location
    }
    Write-Output ("sha: {0}" -f $remoteSha)

    $pythonCommand = Get-PythonCommand
    Write-Output ("Using Python launcher: {0}" -f $pythonCommand.Label)

    $venv = Join-Path $auditRoot "venv"
    & $pythonCommand.Executable @($pythonCommand.Args) -m venv $venv
    if ($LASTEXITCODE -ne 0) {
        throw "venv creation failed with $($pythonCommand.Label)"
    }
    $checksPassed.Add("venv creation completed")

    $pythonExe = Join-Path $venv "Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $pythonExe)) {
        $pythonExe = Join-Path $venv "bin/python"
    }
    if (-not (Test-Path -LiteralPath $pythonExe)) {
        throw "venv Python executable not found"
    }

    & $pythonExe -m pip install $checkout | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "pip install failed"
    }
    $checksPassed.Add("pip install from public clone completed")

    $mapu = Join-Path $venv "Scripts\mapu.exe"
    if (-not (Test-Path -LiteralPath $mapu)) {
        $mapu = Join-Path $venv "bin/mapu"
    }
    if (-not (Test-Path -LiteralPath $mapu)) {
        throw "installed mapu console script not found"
    }

    & $pythonExe -c "import mapu, mapu.cli, mapu.api.app, mapu.mcp.server; from importlib.metadata import metadata; m=metadata('mapu'); assert m['License-Expression']=='AGPL-3.0-only'; assert m['Requires-Python']=='<3.15,>=3.12'; print(mapu.__file__)"
    if ($LASTEXITCODE -ne 0) {
        throw "installed import/metadata check failed"
    }
    $checksPassed.Add("installed import and metadata checks completed")

    & $mapu --help | Out-Null
    & $mapu corpus --help | Out-Null
    & $mapu serve --help | Out-Null
    & $mapu mcp --help | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "installed CLI help check failed"
    }
    $checksPassed.Add("installed CLI help checks completed")

    & $pythonExe (Join-Path $checkout "tools\mcp_stdio_smoke.py") --command $mapu --arg mcp | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "installed MCP stdio smoke failed"
    }
    $checksPassed.Add("installed MCP stdio smoke completed")

    Write-Summary -Passed $true -Sha $remoteSha -ChecksPassed @($checksPassed) -ChecksFailed @()
    Write-Output "Public GitHub install audit passed."
}
catch {
    $checksFailed.Add($_.Exception.Message)
    Write-Summary -Passed $false -Sha $remoteSha -ChecksPassed @($checksPassed) -ChecksFailed @($checksFailed)
    Write-Error ("Public GitHub install audit failed: {0}" -f $_.Exception.Message)
    exit 1
}
finally {
    if (-not $KeepTemp) {
        $auditRoot = Join-Path $repoRoot ".tmp\public-github-install-audit"
        if (Test-Path -LiteralPath $auditRoot) {
            Remove-Item -LiteralPath $auditRoot -Recurse -Force
        }
    }
}
