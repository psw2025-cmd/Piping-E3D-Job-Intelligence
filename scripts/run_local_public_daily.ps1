[CmdletBinding()]
param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$DataRoot = 'E:\Piping-E3D-LocalData\scheduled-public-daily',
    [string]$Sources = 'config\sources.yaml',
    [ValidateRange(1, 1440)][int]$TimeoutMinutes = 120,
    [ValidateRange(0, 3)][int]$Retries = 1,
    [ValidateRange(1, 100)][double]$MinimumFreeGiB = 5,
    [ValidateRange(1, 365)][int]$KeepDays = 14,
    [ValidateRange(1, 100)][int]$KeepRuns = 14,
    [switch]$AllowNoSources,
    [switch]$SkipConnectivity
)

$ErrorActionPreference = 'Stop'
$RepoRoot = [IO.Path]::GetFullPath($RepoRoot)
$Py = Join-Path $RepoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Py -PathType Leaf)) { throw "Repository venv Python not found: $Py" }
$version = & $Py -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($LASTEXITCODE -ne 0 -or $version.Trim() -ne '3.11') { throw 'Python 3.11 repository venv is required' }

$arguments = @(
    '-m', 'job_intelligence.local_runner',
    '--repo', $RepoRoot,
    '--data-root', [IO.Path]::GetFullPath($DataRoot),
    '--sources', $Sources,
    '--timeout-minutes', $TimeoutMinutes,
    '--retries', $Retries,
    '--min-free-gib', $MinimumFreeGiB,
    '--keep-days', $KeepDays,
    '--keep-runs', $KeepRuns
)
if ($AllowNoSources) { $arguments += '--allow-no-sources' }
if ($SkipConnectivity) { $arguments += '--skip-connectivity' }

& $Py @arguments
exit $LASTEXITCODE

<#
Emergency stop:
1. Find the scheduled wrapper/child process in Task Manager or Get-Process python,pwsh.
2. Stop only the identified wrapper process: Stop-Process -Id <PID>.
3. The runner terminates its child process tree on timeout.
4. Never delete the repository. Run outputs stay under -DataRoot.
Laptop sleep/offline:
- Task Scheduler should use StartWhenAvailable and bounded restart settings.
- Connectivity preflight fails closed; the scheduled task retry policy handles recovery.
#>
