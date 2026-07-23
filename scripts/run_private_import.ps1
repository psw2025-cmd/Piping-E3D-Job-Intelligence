[CmdletBinding()]
param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")),
    [string]$Python = ".\.venv\Scripts\python.exe",
    [string]$InputFolder = "private-input",
    [string]$EvidenceFolder = "private-output\evidence",
    [string]$Database = "data\database\jobs.db",
    [string]$Workbook = "data\exports\Piping_E3D_Jobs.xlsx",
    [switch]$EnableOcr,
    [string]$TesseractCommand = ""
)

$ErrorActionPreference = "Stop"
Set-Location $RepoRoot

if (-not (Test-Path $Python)) {
    throw "Virtual-environment Python not found at $Python. Run scripts/install_windows.ps1 first."
}

New-Item -ItemType Directory -Force -Path $InputFolder | Out-Null
New-Item -ItemType Directory -Force -Path $EvidenceFolder | Out-Null
New-Item -ItemType Directory -Force -Path "data\logs" | Out-Null

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$proof = "data\logs\private_import_$timestamp.log"
$arguments = @(
    "-m", "job_intelligence.cli",
    "--db", $Database,
    "import-folder",
    "--folder", $InputFolder,
    "--evidence-dir", $EvidenceFolder,
    "--recursive",
    "--output", $Workbook
)
if ($EnableOcr) {
    $arguments += "--ocr"
}
if ($TesseractCommand) {
    $arguments += @("--tesseract-cmd", $TesseractCommand)
}

& $Python @arguments *>&1 | Tee-Object -FilePath $proof
$importExit = $LASTEXITCODE

if ($importExit -gt 1) {
    throw "Private import failed. See $proof"
}

& $Python -m job_intelligence.cli --db $Database verify --output $Workbook *>&1 |
    Tee-Object -FilePath $proof -Append
if ($LASTEXITCODE -ne 0) {
    throw "Private import verification failed. See $proof"
}

if ($importExit -eq 1) {
    throw "Some private files failed but valid imports were retained. Review $proof"
}

Write-Host "PASS: private vacancy import and verification completed. Proof: $proof"
