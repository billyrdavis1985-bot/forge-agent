# run.ps1 — Windows launcher (PowerShell equivalent of run.sh)
#
# run.sh uses flock, which does not exist on Windows. This reproduces the same
# guarantee with an exclusively-opened lock file: if a second session starts
# while one is running, the open fails and this exits instead of racing on the
# memory directory.
#
# Usage:
#   .\run.ps1
#   .\run.ps1 "your task instruction"

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

# Prefer the project venv; fall back to whatever python is on PATH.
$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$python = if (Test-Path $venvPython) { $venvPython } else { "python" }

# Load .env if present (systemd handles this on Linux; nothing does on Windows).
$envFile = Join-Path $PSScriptRoot ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $idx = $line.IndexOf("=")
            $key = $line.Substring(0, $idx).Trim()
            $val = $line.Substring($idx + 1).Trim().Trim('"')
            [Environment]::SetEnvironmentVariable($key, $val, "Process")
        }
    }
}

# Concurrency guard: exclusive lock, released when the process exits.
$lockPath = Join-Path $PSScriptRoot ".run.lock"
$lock = $null
try {
    $lock = [System.IO.File]::Open(
        $lockPath,
        [System.IO.FileMode]::OpenOrCreate,
        [System.IO.FileAccess]::ReadWrite,
        [System.IO.FileShare]::None
    )
} catch {
    Write-Host "Another session is already running (lock held). Exiting."
    exit 0
}

try {
    & $python -m src.orchestrator @args
    $code = $LASTEXITCODE
} finally {
    if ($lock) { $lock.Close(); $lock.Dispose() }
}

switch ($code) {
    0 { Write-Host "`nRun succeeded." }
    1 { Write-Host "`nRun FAILED (agent error)." -ForegroundColor Red }
    2 { Write-Host "`nPreflight failed (misconfiguration)." -ForegroundColor Yellow }
    3 { Write-Host "`nSkipped: daily budget reached." -ForegroundColor Yellow }
}
exit $code
