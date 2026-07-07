$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$hooksDir = Join-Path $root ".git\hooks"
$source = Join-Path $PSScriptRoot "git-hooks\prepare-commit-msg"
$target = Join-Path $hooksDir "prepare-commit-msg"

Copy-Item -Path $source -Destination $target -Force

$bash = @(
    "$env:ProgramFiles\Git\bin\bash.exe",
    "${env:ProgramFiles(x86)}\Git\bin\bash.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($bash) {
    & $bash -lc "chmod +x '$($target -replace '\\', '/')'"
}

Write-Host "Installed: $target"
