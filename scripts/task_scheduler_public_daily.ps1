[CmdletBinding()]
param(
    [string]$TaskName = 'Piping-E3D-Public-Daily',
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$DataRoot = 'E:\Piping-E3D-LocalData\scheduled-public-daily',
    [datetime]$DailyAt = (Get-Date '06:00'),
    [string]$DryRunOutput = '',
    [switch]$Install
)

$ErrorActionPreference = 'Stop'
$RepoRoot = [IO.Path]::GetFullPath($RepoRoot)
$wrapper = Join-Path $RepoRoot 'scripts\run_local_public_daily.ps1'
if (-not (Test-Path -LiteralPath $wrapper -PathType Leaf)) { throw "Wrapper not found: $wrapper" }
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    throw "Scheduled task already exists; refusing to replace: $TaskName"
}
$pwsh = (Get-Command pwsh.exe -ErrorAction SilentlyContinue).Source
if (-not $pwsh) { $pwsh = (Get-Command powershell.exe -ErrorAction Stop).Source }
$quotedWrapper = '"' + $wrapper + '"'
$quotedRepo = '"' + $RepoRoot + '"'
$quotedData = '"' + [IO.Path]::GetFullPath($DataRoot) + '"'
$action = New-ScheduledTaskAction -Execute $pwsh -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File $quotedWrapper -RepoRoot $quotedRepo -DataRoot $quotedData"
$trigger = New-ScheduledTaskTrigger -Daily -At $DailyAt
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 3) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 30) -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$task = New-ScheduledTask -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Public-only Piping/E3D daily collection; no Gmail or private imports.'
$proof = [ordered]@{
    TaskName = $TaskName
    ExistingTask = $false
    Wrapper = $wrapper
    DataRoot = [IO.Path]::GetFullPath($DataRoot)
    DailyAt = $DailyAt.ToString('HH:mm:ss')
    StartWhenAvailable = $true
    MultipleInstances = 'IgnoreNew'
    RestartCount = 3
    RestartIntervalMinutes = 30
    ExecutionTimeLimitHours = 3
    LogonType = 'Interactive'
    RunLevel = 'Limited'
    RegistrationPerformed = $false
}
if ($DryRunOutput) {
    $parent = Split-Path -Parent ([IO.Path]::GetFullPath($DryRunOutput))
    if ($parent) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    $proof | ConvertTo-Json | Set-Content -LiteralPath $DryRunOutput -Encoding utf8
}
$proof | ConvertTo-Json
if ($Install) {
    throw 'Registration requires explicit final installation approval; rerun only after approval with the registration line enabled.'
}
# Deliberately no task-registration call in this version.
