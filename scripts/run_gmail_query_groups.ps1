[CmdletBinding()]
param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")),
    [string]$Python = ".\.venv\Scripts\python.exe",
    [string]$Credentials = "private-config\gmail_credentials.json",
    [string]$Token = "private-config\gmail_token.json",
    [string]$Database = "data\database\jobs.db",
    [string]$EvidenceFolder = "private-output\gmail-evidence",
    [string]$Workbook = "data\exports\Piping_E3D_Jobs.xlsx"
)

$ErrorActionPreference = "Stop"
Set-Location $RepoRoot

if (-not (Test-Path $Python)) {
    throw "Virtual-environment Python not found at $Python. Run scripts/install_windows.ps1 first."
}
if (-not (Test-Path $Credentials)) {
    throw "Gmail OAuth desktop credentials not found at $Credentials. Follow docs/GMAIL_ALERTS.md."
}

New-Item -ItemType Directory -Force -Path (Split-Path $Token -Parent) | Out-Null
New-Item -ItemType Directory -Force -Path $EvidenceFolder | Out-Null
New-Item -ItemType Directory -Force -Path "data\logs" | Out-Null
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$proof = "data\logs\gmail_groups_$timestamp.log"

& $Python scripts\run_gmail_query_groups.py `
    --db $Database `
    --credentials $Credentials `
    --token $Token `
    --evidence-dir $EvidenceFolder `
    --workbook $Workbook *>&1 | Tee-Object -FilePath $proof
$exitCode = $LASTEXITCODE

if ($exitCode -eq 2) {
    throw "Grouped Gmail alert import or verification failed. See $proof"
}
if ($exitCode -eq 1) {
    throw "Grouped Gmail import retained valid results but some messages failed. Review $proof"
}

Write-Host "PASS: grouped Gmail alerts and worldwide workbook verified. Proof: $proof"
