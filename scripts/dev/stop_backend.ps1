param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [int]$Port = 8765,
    [string]$ListenHost = "127.0.0.1"
)

$ErrorActionPreference = "Stop"

function Get-BackendSessionPaths {
    param([string]$ResolvedProjectRoot)

    $buildRoot = Join-Path $ResolvedProjectRoot "build"
    return @{
        BuildRoot = $buildRoot
        SessionFile = Join-Path $buildRoot ".worker_service.session.json"
        LegacyPidFile = Join-Path $buildRoot ".worker_service.pid"
    }
}

function Get-ListeningProcessId {
    param(
        [string]$Hostname,
        [int]$Port
    )

    try {
        $connections = Get-NetTCPConnection -State Listen -LocalAddress $Hostname -LocalPort $Port -ErrorAction Stop |
            Sort-Object -Property OwningProcess
        foreach ($connection in $connections) {
            if ($connection.OwningProcess -gt 0) {
                return [int]$connection.OwningProcess
            }
        }
    }
    catch {
    }

    try {
        $escaped = [regex]::Escape(("{0}:{1}" -f $Hostname, $Port))
        $lines = netstat -ano -p tcp | Select-String -Pattern $escaped
        foreach ($line in $lines) {
            $text = $line.ToString().Trim()
            if ($text -match "LISTENING\s+(\d+)\s*$") {
                return [int]$matches[1]
            }
        }
    }
    catch {
    }

    return $null
}

function Read-BackendSession {
    param(
        [string]$SessionFile,
        [string]$LegacyPidFile
    )

    if (Test-Path $SessionFile) {
        try {
            $payload = Get-Content $SessionFile -Raw | ConvertFrom-Json -ErrorAction Stop
            return $payload
        }
        catch {
        }
    }

    if (Test-Path $LegacyPidFile) {
        $rawPidText = (Get-Content $LegacyPidFile -Raw).Trim()
        $backendPid = 0
        if ([int]::TryParse($rawPidText, [ref]$backendPid)) {
            return [pscustomobject]@{
                pid = $backendPid
                host = $ListenHost
                port = $Port
            }
        }
    }

    return $null
}

$projectRootResolved = (Resolve-Path $ProjectRoot).Path
$paths = Get-BackendSessionPaths -ResolvedProjectRoot $projectRootResolved
$session = Read-BackendSession -SessionFile $paths.SessionFile -LegacyPidFile $paths.LegacyPidFile

if (-not $session) {
    Write-Host "==> No backend session file found"
    return
}

$backendPid = $null
try {
    if ($null -ne $session.pid -and [int]$session.pid -gt 0) {
        $backendPid = [int]$session.pid
    }
}
catch {
    $backendPid = $null
}

$resolvedHost = if ($session.host) { [string]$session.host } else { $ListenHost }
$resolvedPort = if ($session.port) { [int]$session.port } else { $Port }

if (-not $backendPid) {
    $backendPid = Get-ListeningProcessId -Hostname $resolvedHost -Port $resolvedPort
}

if (-not $backendPid) {
    Remove-Item $paths.SessionFile -ErrorAction SilentlyContinue
    Remove-Item $paths.LegacyPidFile -ErrorAction SilentlyContinue
    Write-Host "==> No backend PID available to stop"
    return
}

try {
    $proc = Get-Process -Id $backendPid -ErrorAction Stop
    Stop-Process -Id $backendPid -Force -ErrorAction Stop
    Write-Host "==> Stopped backend (PID $backendPid)"
}
catch {
    Write-Host "==> Backend PID $backendPid was not running"
}
finally {
    Remove-Item $paths.SessionFile -ErrorAction SilentlyContinue
    Remove-Item $paths.LegacyPidFile -ErrorAction SilentlyContinue
}
