[CmdletBinding()]
param(
    [string]$PythonLauncher = "py"
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

& $PythonLauncher -3.11 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw "Python 3.11 virtual environment creation failed." }

$python = ".\.venv\Scripts\python.exe"
& $python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }

& $python -m pip install -e ".[dev]"
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }

& $python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Tests failed; installation is not accepted." }

Write-Host "PASS: installation and tests completed."
