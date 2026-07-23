param(
    [string]$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")),
    [string]$Database = "data/database/jobs.db",
    [string]$Workbook = "data/exports/Piping_E3D_Jobs.xlsx",
    [string]$Sources = "config/sources.yaml",
    [string]$PublicEvidence = "data/raw",
    [string]$GmailCredentials = "private-input/gmail_credentials.json",
    [string]$GmailToken = "private-output/gmail/token.json",
    [string]$GmailEvidence = "private-output/gmail/evidence",
    [string]$GmailQuery = "newer_than:45d -from:github.com -from:cursor.com " +
        "-from:newsletters-noreply@linkedin.com -subject:electrical " +
        "-subject:structural -subject:`"process engineering`" " +
        "-subject:pipeline -subject:pipelines -subject:cybersecurity " +
        "{from:jobalerts-noreply@linkedin.com from:jobs-noreply@linkedin.com " +
        "from:indeed.com from:gulftalent.com from:jobstreet.com from:naukri.com " +
        "from:bayt.com from:naukrigulf.com from:rigzone.com " +
        "from:energyjobline.com from:oilandgasjobsearch.com " +
        "subject:`"job alert`" subject:`"jobs for you`" subject:`"is hiring`" " +
        "subject:vacancy} " +
        "{piping e3d aveva pdms sp3d `"smart 3d`" `"plant layout`" " +
        "`"pipe support`" `"piping stress`" `"piping designer`"}",
    [int]$GmailMaxMessages = 500,
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
        --query $GmailQuery --max-messages $GmailMaxMessages `
        --evidence-dir $GmailEvidence --output $Workbook --no-export
} else {
    Write-Host "Gmail skipped. Add $GmailCredentials to enable read-only alerts."
}

Invoke-Checked --db $Database export --output $Workbook
Invoke-Checked --db $Database verify --output $Workbook
Write-Host "PASS: worldwide daily workbook is ready at $Workbook"
