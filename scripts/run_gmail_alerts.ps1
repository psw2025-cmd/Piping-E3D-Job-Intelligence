[CmdletBinding()]
param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")),
    [string]$Python = ".\.venv\Scripts\python.exe",
    [string]$Credentials = "private-config\gmail_credentials.json",
    [string]$Token = "private-config\gmail_token.json",
    [string]$Database = "data\database\jobs.db",
    [string]$EvidenceFolder = "private-output\gmail-evidence",
    [string]$Workbook = "data\exports\Piping_E3D_Jobs.xlsx",
    [string]$Query = "newer_than:30d (job OR jobs OR vacancy OR vacancies OR hiring OR career)",
    [int]$MaxMessages = 200
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
$proof = "data\logs\gmail_import_$timestamp.log"

& $Python -m job_intelligence.cli --db $Database gmail-import `
    --credentials $Credentials `
    --token $Token `
    --query $Query `
    --max-messages $MaxMessages `
    --evidence-dir $EvidenceFolder `
    --output $Workbook *>&1 | Tee-Object -FilePath $proof
$importExit = $LASTEXITCODE

if ($importExit -gt 1) {
    throw "Gmail alert import failed. See $proof"
}

& $Python -m job_intelligence.cli --db $Database verify --output $Workbook *>&1 |
    Tee-Object -FilePath $proof -Append
if ($LASTEXITCODE -ne 0) {
    throw "Gmail alert verification failed. See $proof"
}

if ($importExit -eq 1) {
    throw "Some Gmail messages failed but valid imports were retained. Review $proof"
}

Write-Host "PASS: Gmail alerts imported and verified. Proof: $proof"
