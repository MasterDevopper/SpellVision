param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
)

$ErrorActionPreference = "Stop"

$projectRootResolved = (Resolve-Path $ProjectRoot).Path
$buildRoot = Join-Path $projectRootResolved "build"
$sessionFile = Join-Path $buildRoot ".comfy_runtime.session.json"
$legacyPidFile = Join-Path $buildRoot ".comfy_runtime.pid"

if (-not (Test-Path $sessionFile)) {
    if (Test-Path $legacyPidFile) {
        $pidText = (Get-Content $legacyPidFile -Raw).Trim()
        if ($pidText -match "^\d+$") {
            Stop-Process -Id ([int]$pidText) -Force -ErrorAction SilentlyContinue
        }
        Remove-Item $legacyPidFile -Force -ErrorAction SilentlyContinue
    }

    return
}

$session = Get-Content $sessionFile -Raw | ConvertFrom-Json

# Only stop Comfy if this script started it. If the user had Comfy running before
# SpellVision launched, adopt it but leave it running on exit.
if ($session.started_by_script -eq $true -and $session.pid) {
    try {
        Stop-Process -Id ([int]$session.pid) -Force -ErrorAction SilentlyContinue
        Write-Host "==> Stopped ComfyUI session (PID $($session.pid))"
    }
    catch {
        Write-Warning "Failed to stop ComfyUI session: $($_.Exception.Message)"
    }
}
else {
    Write-Host "==> Leaving adopted ComfyUI session running"
}

Remove-Item $sessionFile -Force -ErrorAction SilentlyContinue
Remove-Item $legacyPidFile -Force -ErrorAction SilentlyContinue
