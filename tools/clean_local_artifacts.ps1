Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location -LiteralPath $repoRoot

$workspace = (Resolve-Path -LiteralPath ".").Path

# Do not remove `.tmp/memory-benchmarks`: benchmark runners load it at runtime.
$targets = @(
    ".benchmarks",
    ".codex_tmp",
    ".coverage",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".uv-cache",
    "dist"
)

$tmpRoot = Join-Path $repoRoot ".tmp"
if (Test-Path -LiteralPath $tmpRoot) {
    Get-ChildItem -LiteralPath $tmpRoot -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -ne "memory-benchmarks" } |
        ForEach-Object { $targets += $_.FullName }
}

Get-ChildItem -LiteralPath "src", "tests", "tools" -Force -Directory -Recurse -Filter "__pycache__" -ErrorAction SilentlyContinue |
    ForEach-Object { $targets += $_.FullName }

foreach ($target in ($targets | Sort-Object -Unique)) {
    if (-not (Test-Path -LiteralPath $target)) {
        continue
    }
    $resolved = (Resolve-Path -LiteralPath $target).Path
    if (-not ($resolved -eq $workspace -or $resolved.StartsWith($workspace + [IO.Path]::DirectorySeparatorChar))) {
        throw "Refusing cleanup outside workspace: $resolved"
    }
    Write-Output "Removing $resolved"
    Remove-Item -LiteralPath $resolved -Recurse -Force -ErrorAction Stop
}

Write-Output "Local artifact cleanup complete."
