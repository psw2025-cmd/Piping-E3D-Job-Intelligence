param(
    [string]$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")),
    [string]$Database = "data/database/jobs.db",
    [string]$Workbook = "data/exports/Piping_E3D_Jobs.xlsx",
    [string]$Sources = "config/sources.yaml",
    [string]$PublicEvidence = "data/raw",
    [string]$PrivateEvidence = "private-output/evidence",
    [string]$GmailCredentials = "private-input/gmail_credentials.json",
    [string]$GmailToken = "private-output/gmail/token.json",
    [int]$GmailMaxResults = 200,
    [switch]$SkipGmail
)

$ErrorActionPreference = "Stop"
Set-Location $RepositoryRoot
$Python = Join-Path $RepositoryRoot ".venv/Scripts/python.exe"
if (-not (Test-Path $Python)) {
    throw "Python virtual environment not found: $Python"
}

function Invoke-Checked {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE: $($Arguments -join ' ')"
    }
}

Write-Host "[1/4] Collecting verified worldwide public sources..."
Invoke-Checked -m job_intelligence.cli --db $Database collect `
    --sources $Sources --evidence-dir $PublicEvidence --output $Workbook --no-export

if (-not $SkipGmail -and (Test-Path $GmailCredentials)) {
    Write-Host "[2/4] Importing authorized Gmail job alerts..."
    Invoke-Checked scripts/import_gmail_alerts.py `
        --db $Database --credentials $GmailCredentials --token $GmailToken `
        --max-results $GmailMaxResults --evidence-dir $PrivateEvidence `
        --output $Workbook --no-export
} else {
    Write-Host "[2/4] Gmail skipped. Add $GmailCredentials to enable read-only alerts."
}

Write-Host "[3/4] Exporting worldwide deduplicated workbook..."
Invoke-Checked -m job_intelligence.cli --db $Database export --output $Workbook

Write-Host "[4/4] Verifying database, evidence and workbook..."
Invoke-Checked -m job_intelligence.cli --db $Database verify --output $Workbook
Write-Host "PASS: worldwide daily workbook is ready at $Workbook"
