param(
    [string]$TaskName = "PipingE3D_Worldwide_Daily",
    [string]$RunTime = "09:15",
    [string]$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot ".."))
)

$ErrorActionPreference = "Stop"
$Runner = Join-Path $RepositoryRoot "scripts/run_worldwide_daily.ps1"
if (-not (Test-Path $Runner)) {
    throw "Worldwide runner not found: $Runner"
}

$PowerShell = (Get-Command powershell.exe -ErrorAction Stop).Source
$Action = New-ScheduledTaskAction `
    -Execute $PowerShell `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Runner`""
$Trigger = New-ScheduledTaskTrigger -Daily -At $RunTime
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Build the verified worldwide piping/E3D job workbook daily." `
    -Force | Out-Null

Write-Host "PASS: scheduled task '$TaskName' installed for $RunTime local time."
Write-Host "Run manually: Start-ScheduledTask -TaskName '$TaskName'"
