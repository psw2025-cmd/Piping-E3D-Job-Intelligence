[CmdletBinding()]
param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")),
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
Set-Location $RepoRoot

if (-not (Test-Path $Python)) {
    throw "Virtual-environment Python not found at $Python. Run scripts/install_windows.ps1 first."
}

$db = "data\database\jobs.db"
$xlsx = "data\exports\Piping_E3D_Jobs.xlsx"
$sources = "config\sources.yaml"
$evidence = "data\raw"
$proofDir = "data\logs"
New-Item -ItemType Directory -Force -Path $proofDir | Out-Null
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$proof = Join-Path $proofDir "daily_run_$timestamp.log"

& $Python -m job_intelligence.cli validate-sources --sources $sources *>&1 |
    Tee-Object -FilePath $proof
if ($LASTEXITCODE -ne 0) {
    throw "Source configuration validation failed. See $proof"
}

& $Python -m job_intelligence.cli --db $db collect `
    --sources $sources `
    --evidence-dir $evidence `
    --output $xlsx *>&1 |
    Tee-Object -FilePath $proof -Append
if ($LASTEXITCODE -ne 0) {
    throw "Collection was partial or failed. Review Source_Health and $proof"
}

& $Python -m job_intelligence.cli --db $db verify --output $xlsx *>&1 |
    Tee-Object -FilePath $proof -Append
if ($LASTEXITCODE -ne 0) {
    throw "Verification failed. See $proof"
}

Write-Host "PASS: daily collection, export and verification completed. Proof: $proof"
