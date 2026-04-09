param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$PythonExe = "",
    [int]$Port = 8765,
    [int]$StartupTimeoutSec = 30,
    [string]$ListenHost = "127.0.0.1"
)

$ErrorActionPreference = "Stop"

function Test-PortListening {
    param(
        [string]$Hostname,
        [int]$Port
    )

    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $iar = $client.BeginConnect($Hostname, $Port, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne(500)
        if (-not $ok) {
            $client.Close()
            return $false
        }
        $client.EndConnect($iar)
        $client.Close()
        return $true
    }
    catch {
        return $false
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

function Get-ProcessCommandLine {
    param([int]$ProcessId)

    try {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction Stop
        return [string]$proc.CommandLine
    }
    catch {
        return ""
    }
}

function Get-BackendSessionPaths {
    param([string]$ResolvedProjectRoot)

    $buildRoot = Join-Path $ResolvedProjectRoot "build"
    return @{
        BuildRoot = $buildRoot
        SessionFile = Join-Path $buildRoot ".worker_service.session.json"
        LegacyPidFile = Join-Path $buildRoot ".worker_service.pid"
        StdoutLog = Join-Path $buildRoot "worker_service.stdout.log"
        StderrLog = Join-Path $buildRoot "worker_service.stderr.log"
    }
}

function Write-BackendSession {
    param(
        [string]$SessionFile,
        [string]$LegacyPidFile,
        [hashtable]$Payload
    )

    $json = $Payload | ConvertTo-Json -Depth 8
    Set-Content -Path $SessionFile -Value $json -Encoding UTF8
    if ($Payload.ContainsKey("pid") -and $null -ne $Payload.pid) {
        Set-Content -Path $LegacyPidFile -Value ([string]$Payload.pid) -Encoding ASCII
    }
}

$projectRootResolved = (Resolve-Path $ProjectRoot).Path
$workerScript = Join-Path $projectRootResolved "python\worker_service.py"

if (-not (Test-Path $workerScript)) {
    throw "worker_service.py not found at $workerScript"
}

if (-not $PythonExe) {
    $venvPython = Join-Path $projectRootResolved ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        $PythonExe = $venvPython
    }
    else {
        $PythonExe = "python"
    }
}

$paths = Get-BackendSessionPaths -ResolvedProjectRoot $projectRootResolved
New-Item -ItemType Directory -Force -Path $paths.BuildRoot | Out-Null

if (Test-PortListening -Hostname $ListenHost -Port $Port) {
    $existingPid = Get-ListeningProcessId -Hostname $ListenHost -Port $Port
    $commandLine = if ($existingPid) { Get-ProcessCommandLine -ProcessId $existingPid } else { "" }
    Write-BackendSession -SessionFile $paths.SessionFile -LegacyPidFile $paths.LegacyPidFile -Payload @{
        pid = $existingPid
        host = $ListenHost
        port = $Port
        project_root = $projectRootResolved
        python_exe = $PythonExe
        worker_script = $workerScript
        adopted_existing = $true
        started_by_script = $false
        command_line = $commandLine
        detected_at = (Get-Date).ToString("o")
    }
    Write-Host "==> Backend already listening on ${ListenHost}:$Port" + $(if ($existingPid) { " (PID $existingPid)" } else { "" })
    return
}

$proc = Start-Process `
    -FilePath $PythonExe `
    -ArgumentList $workerScript `
    -WorkingDirectory $projectRootResolved `
    -RedirectStandardOutput $paths.StdoutLog `
    -RedirectStandardError $paths.StderrLog `
    -PassThru `
    -WindowStyle Hidden

$deadline = (Get-Date).AddSeconds($StartupTimeoutSec)
while ((Get-Date) -lt $deadline) {
    if (Test-PortListening -Hostname $ListenHost -Port $Port) {
        $activePid = Get-ListeningProcessId -Hostname $ListenHost -Port $Port
        if (-not $activePid) {
            $activePid = $proc.Id
        }
        Write-BackendSession -SessionFile $paths.SessionFile -LegacyPidFile $paths.LegacyPidFile -Payload @{
            pid = $activePid
            host = $ListenHost
            port = $Port
            project_root = $projectRootResolved
            python_exe = $PythonExe
            worker_script = $workerScript
            adopted_existing = $false
            started_by_script = $true
            launcher_pid = $proc.Id
            command_line = Get-ProcessCommandLine -ProcessId $activePid
            detected_at = (Get-Date).ToString("o")
        }
        Write-Host "==> Backend listening on ${ListenHost}:$Port (PID $activePid)"
        return
    }

    if ($proc.HasExited) {
        $stderr = ""
        if (Test-Path $paths.StderrLog) {
            $stderr = Get-Content $paths.StderrLog -Raw
        }
        throw "worker_service.py exited early. STDERR:`n$stderr"
    }

    Start-Sleep -Milliseconds 500
}

try {
    if (-not $proc.HasExited) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
}
catch {
}

throw "Timed out waiting for worker_service.py to listen on ${ListenHost}:$Port"
