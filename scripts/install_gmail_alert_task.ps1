[CmdletBinding()]
param(
    [string]$TaskName = "Piping-E3D-Gmail-Alerts",
    [string]$DailyTime = "09:15",
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot ".."))
)

$ErrorActionPreference = "Stop"

try {
    $scheduledTime = [DateTime]::ParseExact(
        $DailyTime,
        "HH:mm",
        [Globalization.CultureInfo]::InvariantCulture
    )
} catch {
    throw "DailyTime must use 24-hour HH:mm format, for example 09:15."
}

$runner = Join-Path $RepoRoot "scripts\run_gmail_alerts.ps1"
if (-not (Test-Path $runner)) {
    throw "Gmail runner not found: $runner"
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runner`""
$trigger = New-ScheduledTaskTrigger -Daily -At $scheduledTime
$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Imports user-authorized Gmail job alerts into the private piping/E3D tracker." `
    -Force | Out-Null

Write-Host "PASS: task '$TaskName' registered for $DailyTime local time."
Write-Host "The task runs only while the Windows user is logged in."
