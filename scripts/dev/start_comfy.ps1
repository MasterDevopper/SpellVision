param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$PythonExe = "",
    [string]$ComfyRoot = "C:\sv_comfynext\ComfyUI",
    [string]$ListenHost = "127.0.0.1",
    [int]$Port = 8188,
    [int]$StartupTimeoutSec = 90
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

function Test-ComfyHealthy {
    param(
        [string]$Hostname,
        [int]$Port
    )

    try {
        $uri = "http://${Hostname}:$Port/system_stats"
        $null = Invoke-RestMethod -Uri $uri -Method Get -TimeoutSec 3
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

function Get-ComfySessionPaths {
    param([string]$ResolvedProjectRoot)

    $buildRoot = Join-Path $ResolvedProjectRoot "build"
    return @{
        BuildRoot = $buildRoot
        SessionFile = Join-Path $buildRoot ".comfy_runtime.session.json"
        LegacyPidFile = Join-Path $buildRoot ".comfy_runtime.pid"
        StdoutLog = Join-Path $buildRoot "comfy_runtime.stdout.log"
        StderrLog = Join-Path $buildRoot "comfy_runtime.stderr.log"
    }
}

function Write-ComfySession {
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

if (-not $PythonExe) {
    # Cutover (Doc 25): prefer ComfyUI's OWN isolated venv (Jul-10 core deps), then the project venv.
    $comfyVenv = "C:\sv_comfynext\.venv\Scripts\python.exe"
    $venvPython = Join-Path $projectRootResolved ".venv\Scripts\python.exe"
    if (Test-Path $comfyVenv) {
        $PythonExe = $comfyVenv
    }
    elseif (Test-Path $venvPython) {
        $PythonExe = $venvPython
    }
    else {
        $PythonExe = "python"
    }
}

if (-not (Test-Path $ComfyRoot)) {
    throw "ComfyUI root not found: $ComfyRoot"
}

$comfyMain = Join-Path $ComfyRoot "main.py"
if (-not (Test-Path $comfyMain)) {
    throw "ComfyUI main.py not found at $comfyMain"
}

$paths = Get-ComfySessionPaths -ResolvedProjectRoot $projectRootResolved
New-Item -ItemType Directory -Force -Path $paths.BuildRoot | Out-Null

if (Test-PortListening -Hostname $ListenHost -Port $Port) {
    $existingPid = Get-ListeningProcessId -Hostname $ListenHost -Port $Port
    $healthy = Test-ComfyHealthy -Hostname $ListenHost -Port $Port
    $commandLine = if ($existingPid) { Get-ProcessCommandLine -ProcessId $existingPid } else { "" }

    Write-ComfySession -SessionFile $paths.SessionFile -LegacyPidFile $paths.LegacyPidFile -Payload @{
        pid = $existingPid
        host = $ListenHost
        port = $Port
        project_root = $projectRootResolved
        python_exe = $PythonExe
        comfy_root = $ComfyRoot
        comfy_main = $comfyMain
        adopted_existing = $true
        started_by_script = $false
        healthy = $healthy
        command_line = $commandLine
        detected_at = (Get-Date).ToString("o")
    }

    if ($healthy) {
        Write-Host "==> ComfyUI already healthy on http://${ListenHost}:$Port" + $(if ($existingPid) { " (PID $existingPid)" } else { "" })
        return
    }

    throw "Port ${ListenHost}:$Port is listening, but ComfyUI /system_stats is not healthy."
}

$arguments = @(
    $comfyMain,
    "--listen", $ListenHost,
    "--port", ([string]$Port)
)

# Gated-ComfyUI-update cutover (2026-07-17, Doc 25 S1): the Jul-10 RES4LYF pack ships non-ASCII (a Greek
# delta in a matplotlib label) that crashes ComfyUI's stderr logging under Windows cp1252 -> whole process
# dies. Force utf-8 so node-import errors log cleanly. Harmless on the old build.
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$proc = Start-Process `
    -FilePath $PythonExe `
    -ArgumentList $arguments `
    -WorkingDirectory $ComfyRoot `
    -RedirectStandardOutput $paths.StdoutLog `
    -RedirectStandardError $paths.StderrLog `
    -PassThru `
    -WindowStyle Hidden

$deadline = (Get-Date).AddSeconds($StartupTimeoutSec)
while ((Get-Date) -lt $deadline) {
    if (Test-ComfyHealthy -Hostname $ListenHost -Port $Port) {
        $activePid = Get-ListeningProcessId -Hostname $ListenHost -Port $Port
        if (-not $activePid) {
            $activePid = $proc.Id
        }

        Write-ComfySession -SessionFile $paths.SessionFile -LegacyPidFile $paths.LegacyPidFile -Payload @{
            pid = $activePid
            host = $ListenHost
            port = $Port
            project_root = $projectRootResolved
            python_exe = $PythonExe
            comfy_root = $ComfyRoot
            comfy_main = $comfyMain
            adopted_existing = $false
            started_by_script = $true
            launcher_pid = $proc.Id
            healthy = $true
            command_line = Get-ProcessCommandLine -ProcessId $activePid
            detected_at = (Get-Date).ToString("o")
        }

        Write-Host "==> ComfyUI healthy on http://${ListenHost}:$Port (PID $activePid)"
        return
    }

    if ($proc.HasExited) {
        $stderr = ""
        if (Test-Path $paths.StderrLog) {
            $stderr = Get-Content $paths.StderrLog -Raw
        }

        throw "ComfyUI exited early. STDERR:`n$stderr"
    }

    Start-Sleep -Milliseconds 750
}

try {
    if (-not $proc.HasExited) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
}
catch {
}

$stderrTail = ""
if (Test-Path $paths.StderrLog) {
    $stderrTail = Get-Content $paths.StderrLog -Tail 80 | Out-String
}

throw "Timed out waiting for ComfyUI /system_stats on http://${ListenHost}:$Port.`nSTDERR tail:`n$stderrTail"
