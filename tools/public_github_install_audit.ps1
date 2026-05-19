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

function Write-JsonUtf8NoBom {
    param(
        [object]$Data,
        [string]$Path,
        [int]$Depth = 5
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

function Write-Summary {
    param(
        [bool]$Passed,
        [string]$Sha,
        [string[]]$ChecksPassed,
        [string[]]$ChecksFailed,
        [object[]]$CliHelpEvidence = @(),
        [object]$DoctorEvidence = $null,
        [object]$McpSmokeEvidence = $null
    )
    if ([string]::IsNullOrWhiteSpace($OutputJson)) {
        return
    }
    $summary = [ordered]@{
        repo_url = $RepoUrl
        ref = $Ref
        sha = $Sha
        passed = $Passed
        cli_help_evidence = @($CliHelpEvidence)
        doctor_evidence = $DoctorEvidence
        mcp_stdio_smoke = $McpSmokeEvidence
        checks_passed = $ChecksPassed
        checks_failed = $ChecksFailed
    }
    Write-JsonUtf8NoBom -Data $summary -Path $OutputJson -Depth 5
}

$checksPassed = New-Object System.Collections.Generic.List[string]
$checksFailed = New-Object System.Collections.Generic.List[string]
$cliHelpEvidence = New-Object System.Collections.Generic.List[object]
$doctorEvidence = $null
$mcpSmokeEvidence = $null
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

    $helpFailureCount = $checksFailed.Count
    foreach ($helpArgs in @(
            @("--help"),
            @("corpus", "--help"),
            @("serve", "--help"),
            @("doctor", "--help"),
            @("mcp", "--help")
        )) {
        & $mapu @helpArgs | Out-Null
        if ($LASTEXITCODE -ne 0) {
            $checksFailed.Add("installed CLI help check failed: mapu $($helpArgs -join ' ')")
            $cliHelpEvidence.Add([ordered]@{
                command = [string[]](@($mapu) + @($helpArgs))
                status = "fail"
                exit_code = $LASTEXITCODE
            })
            continue
        }
        $cliHelpEvidence.Add([ordered]@{
            command = [string[]](@($mapu) + @($helpArgs))
            status = "ok"
            exit_code = 0
        })
    }
    if ($checksFailed.Count -eq $helpFailureCount) {
        $checksPassed.Add("installed CLI help checks completed")
    }

    $doctorJsonPath = Join-Path $auditRoot "mapu_doctor.json"
    & $mapu doctor --json > $doctorJsonPath
    if ($LASTEXITCODE -ne 0) {
        $checksFailed.Add("installed doctor check failed")
    } else {
        $doctorEvidence = Get-Content -LiteralPath $doctorJsonPath -Raw | ConvertFrom-Json
        if ($doctorEvidence.status -ne "ok") {
            $checksFailed.Add("installed doctor status is not ok")
        } else {
            $checksPassed.Add("installed doctor check completed")
        }
    }

    Push-Location -LiteralPath $checkout
    try {
        $localMcpSmoke = Join-Path $repoRoot "tools\mcp_stdio_smoke.py"
        $mcpSmokePath = Join-Path $checkout "logs\mcp_stdio_smoke_last.json"
        $mcpSmokeStdout = Join-Path $auditRoot "mcp_stdio_smoke.stdout.log"
        $mcpSmokeStderr = Join-Path $auditRoot "mcp_stdio_smoke.stderr.log"
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            & $pythonExe $localMcpSmoke `
                --command $mapu `
                --arg mcp `
                --cwd $checkout `
                --list-only `
                --out $mcpSmokePath `
                --json 1> $mcpSmokeStdout 2> $mcpSmokeStderr
        }
        finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
        $mcpSmokeStdoutText = if (Test-Path -LiteralPath $mcpSmokeStdout) {
            Get-Content -LiteralPath $mcpSmokeStdout -Raw
        } else {
            ""
        }
        $mcpSmokeStderrText = if (Test-Path -LiteralPath $mcpSmokeStderr) {
            Get-Content -LiteralPath $mcpSmokeStderr -Raw
        } else {
            ""
        }
        $mcpSmokeText = (($mcpSmokeStdoutText, $mcpSmokeStderrText) -join "`n").Trim()
        if (Test-Path -LiteralPath $mcpSmokePath) {
            $mcpSmokeEvidence = Get-Content -LiteralPath $mcpSmokePath -Raw | ConvertFrom-Json
        } elseif (-not [string]::IsNullOrWhiteSpace($mcpSmokeStdoutText)) {
            $jsonStart = $mcpSmokeStdoutText.IndexOf("{")
            if ($jsonStart -ge 0) {
                $jsonText = $mcpSmokeStdoutText.Substring($jsonStart)
                try {
                    $mcpSmokeEvidence = $jsonText | ConvertFrom-Json
                } catch {
                    $mcpSmokeEvidence = $null
                }
            }
        }
        if ($LASTEXITCODE -ne 0) {
            if ($null -ne $mcpSmokeEvidence -and $mcpSmokeEvidence.missing_required_tools) {
                $checksFailed.Add(
                    "installed MCP stdio smoke failed: missing required tools: {0}" -f
                    (($mcpSmokeEvidence.missing_required_tools | ForEach-Object { $_.ToString() }) -join ", ")
                )
            } elseif ([string]::IsNullOrWhiteSpace($mcpSmokeText)) {
                $checksFailed.Add("installed MCP stdio smoke failed")
            } else {
                $checksFailed.Add("installed MCP stdio smoke failed: {0}" -f $mcpSmokeText)
            }
        } elseif (-not (Test-Path -LiteralPath $mcpSmokePath)) {
            $checksFailed.Add("installed MCP stdio smoke evidence not found: $mcpSmokePath")
        } else {
            $checksPassed.Add("installed MCP stdio smoke completed")
        }
    }
    finally {
        Pop-Location
    }

    if ($checksFailed.Count -gt 0) {
        Write-Summary `
            -Passed $false `
            -Sha $remoteSha `
            -ChecksPassed @($checksPassed) `
            -ChecksFailed @($checksFailed) `
            -CliHelpEvidence @($cliHelpEvidence.ToArray()) `
            -DoctorEvidence $doctorEvidence `
            -McpSmokeEvidence $mcpSmokeEvidence
        [Console]::Error.WriteLine("Public GitHub install audit failed: {0}" -f ($checksFailed -join "; "))
        exit 1
    }

    Write-Summary `
        -Passed $true `
        -Sha $remoteSha `
        -ChecksPassed @($checksPassed) `
        -ChecksFailed @() `
        -CliHelpEvidence @($cliHelpEvidence.ToArray()) `
        -DoctorEvidence $doctorEvidence `
        -McpSmokeEvidence $mcpSmokeEvidence
    Write-Output "Public GitHub install audit passed."
}
catch {
    $checksFailed.Add($_.Exception.Message)
    Write-Summary `
        -Passed $false `
        -Sha $remoteSha `
        -ChecksPassed @($checksPassed) `
        -ChecksFailed @($checksFailed) `
        -CliHelpEvidence @($cliHelpEvidence.ToArray()) `
        -DoctorEvidence $doctorEvidence `
        -McpSmokeEvidence $mcpSmokeEvidence
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
