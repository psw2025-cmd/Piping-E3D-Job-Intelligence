param(
    [string]$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")),
    [string]$Database = "data/database/jobs.db",
    [string]$Workbook = "data/exports/Piping_E3D_Jobs.xlsx",
    [string]$Sources = "config/sources.yaml",
    [string]$PublicEvidence = "data/raw",
    [string]$GmailCredentials = "private-input/gmail_credentials.json",
    [string]$GmailToken = "private-output/gmail/token.json",
    [string]$GmailEvidence = "private-output/gmail/evidence",
    [int]$GmailMaxMessages = 200,
    [switch]$SkipGmail
)

$ErrorActionPreference = "Stop"
Set-Location $RepositoryRoot
$Python = Join-Path $RepositoryRoot ".venv/Scripts/python.exe"
if (-not (Test-Path $Python)) { throw "Python virtual environment not found: $Python" }

function Invoke-Checked {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & $Python -m job_intelligence.cli @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "job-intel failed with exit code $LASTEXITCODE: $($Arguments -join ' ')"
    }
}

Invoke-Checked --db $Database collect `
    --sources $Sources --evidence-dir $PublicEvidence --output $Workbook --no-export

if (-not $SkipGmail -and (Test-Path $GmailCredentials)) {
    Invoke-Checked --db $Database gmail-import `
        --credentials $GmailCredentials --token $GmailToken `
        --max-messages $GmailMaxMessages --evidence-dir $GmailEvidence `
        --output $Workbook --no-export
} else {
    Write-Host "Gmail skipped. Add $GmailCredentials to enable read-only alerts."
}

Invoke-Checked --db $Database export --output $Workbook
Invoke-Checked --db $Database verify --output $Workbook
Write-Host "PASS: worldwide daily workbook is ready at $Workbook"
