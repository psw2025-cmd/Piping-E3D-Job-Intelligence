[CmdletBinding()]
param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")),
    [string]$TaskName = "PipingE3D_PrivateJobImport",
    [string]$DailyTime = "09:30",
    [switch]$EnableOcr,
    [string]$TesseractCommand = ""
)

$ErrorActionPreference = "Stop"
$runner = Join-Path $RepoRoot "scripts\run_private_import.ps1"
if (-not (Test-Path $runner)) {
    throw "Private import runner not found: $runner"
}

$argumentParts = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", ('"{0}"' -f $runner),
    "-RepoRoot", ('"{0}"' -f $RepoRoot)
)
if ($EnableOcr) {
    $argumentParts += "-EnableOcr"
}
if ($TesseractCommand) {
    $argumentParts += @("-TesseractCommand", ('"{0}"' -f $TesseractCommand))
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument ($argumentParts -join " ") `
    -WorkingDirectory $RepoRoot
$trigger = New-ScheduledTaskTrigger -Daily -At $DailyTime
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)
$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Import private piping/E3D vacancy files, export Excel, and verify evidence." `
    -Force | Out-Null

$task = Get-ScheduledTask -TaskName $TaskName
Write-Host "PASS: scheduled task installed: $($task.TaskName)"
Write-Host "Schedule: daily at $DailyTime local Windows time"
Write-Host "Runner: $runner"
