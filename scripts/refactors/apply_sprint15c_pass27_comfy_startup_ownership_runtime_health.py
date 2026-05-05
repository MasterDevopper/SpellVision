from pathlib import Path
import re

root = Path(".")
run_ui_path = root / "scripts" / "dev" / "run_ui.ps1"
start_comfy_path = root / "scripts" / "dev" / "start_comfy.ps1"
stop_comfy_path = root / "scripts" / "dev" / "stop_comfy.ps1"
t2v_cpp_path = root / "qt_ui" / "T2VHistoryPage.cpp"
doc_path = root / "docs" / "sprints" / "SPRINT15C_PASS27_COMFY_STARTUP_OWNERSHIP_RUNTIME_HEALTH_README.md"
script_path = root / "scripts" / "refactors" / "apply_sprint15c_pass27_comfy_startup_ownership_runtime_health.py"

run_ui = run_ui_path.read_text(encoding="utf-8")
t2v = t2v_cpp_path.read_text(encoding="utf-8")

# ----------------------------------------------------------------------
# 1) Add start_comfy.ps1
# ----------------------------------------------------------------------

start_comfy_path.write_text(r'''param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$PythonExe = "",
    [string]$ComfyRoot = "D:\AI_ASSETS\comfy_runtime\ComfyUI",
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
    $venvPython = Join-Path $projectRootResolved ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
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
''', encoding="utf-8")


# ----------------------------------------------------------------------
# 2) Add stop_comfy.ps1
# ----------------------------------------------------------------------

stop_comfy_path.write_text(r'''param(
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
''', encoding="utf-8")


# ----------------------------------------------------------------------
# 3) Patch run_ui.ps1: params + start/stop Comfy lifecycle.
# ----------------------------------------------------------------------

if "[switch]$NoComfy" not in run_ui:
    run_ui = run_ui.replace(
        '''param(
    [string]$QtRoot = "",
    [switch]$NoBackend,
    [switch]$NoTranslations,
    [switch]$FastDeploy
)''',
        '''param(
    [string]$QtRoot = "",
    [switch]$NoBackend,
    [switch]$NoComfy,
    [string]$ComfyRoot = "D:\\AI_ASSETS\\comfy_runtime\\ComfyUI",
    [int]$ComfyPort = 8188,
    [switch]$NoTranslations,
    [switch]$FastDeploy
)''',
        1,
    )

if "$comfySessionAcquired" not in run_ui:
    run_ui = run_ui.replace(
        '''$backendSessionAcquired = $false''',
        '''$backendSessionAcquired = $false
$comfySessionAcquired = $false''',
        1,
    )

if "==> Ensuring ComfyUI session" not in run_ui:
    run_ui = run_ui.replace(
        '''    if (-not $NoBackend) {
        Write-Host "==> Ensuring backend session"
        & (Join-Path $PSScriptRoot "start_backend.ps1") -ProjectRoot $projectRoot -PythonExe $pythonExe
        if ($LASTEXITCODE -ne 0) {
            throw "Backend start failed."
        }
        $backendSessionAcquired = $true
    }

    Write-Host "==> Launching UI"''',
        '''    if (-not $NoBackend) {
        Write-Host "==> Ensuring backend session"
        & (Join-Path $PSScriptRoot "start_backend.ps1") -ProjectRoot $projectRoot -PythonExe $pythonExe
        if ($LASTEXITCODE -ne 0) {
            throw "Backend start failed."
        }
        $backendSessionAcquired = $true
    }

    if (-not $NoComfy) {
        Write-Host "==> Ensuring ComfyUI session"
        & (Join-Path $PSScriptRoot "start_comfy.ps1") -ProjectRoot $projectRoot -PythonExe $pythonExe -ComfyRoot $ComfyRoot -Port $ComfyPort
        if ($LASTEXITCODE -ne 0) {
            throw "ComfyUI start failed."
        }
        $comfySessionAcquired = $true
    }

    Write-Host "==> Launching UI"''',
        1,
    )

if "Stopping ComfyUI session" not in run_ui:
    run_ui = run_ui.replace(
        '''finally {
    if ($backendSessionAcquired) {''',
        '''finally {
    if ($comfySessionAcquired) {
        Write-Host "==> Stopping ComfyUI session"
        try {
            & (Join-Path $PSScriptRoot "stop_comfy.ps1") -ProjectRoot $projectRoot
        }
        catch {
            Write-Warning "Failed to stop ComfyUI session: $($_.Exception.Message)"
        }
    }

    if ($backendSessionAcquired) {''',
        1,
    )

run_ui_path.write_text(run_ui, encoding="utf-8")


# ----------------------------------------------------------------------
# 4) T2V submit preflight: block before confirmation if Comfy is offline.
# ----------------------------------------------------------------------

if "#include <QTcpSocket>" not in t2v:
    t2v = t2v.replace("#include <QTimer>", "#include <QTimer>\n#include <QTcpSocket>", 1)

preflight_helpers = r'''
bool isComfyPromptApiReachable(const QString &host = QStringLiteral("127.0.0.1"), int port = 8188, int timeoutMs = 750)
{
    QTcpSocket socket;
    socket.connectToHost(host, static_cast<quint16>(port));

    if (!socket.waitForConnected(timeoutMs))
        return false;

    socket.disconnectFromHost();
    return true;
}

QString comfyOfflineMessage()
{
    return QStringLiteral(
        "ComfyUI is not reachable at http://127.0.0.1:8188.\n\n"
        "SpellVision's worker can be ready while ComfyUI is offline. "
        "Start ComfyUI first, or launch SpellVision through scripts/dev/run_ui.ps1 without -NoComfy.\n\n"
        "Submit Requeue is blocked until ComfyUI is reachable.");
}

'''

if "isComfyPromptApiReachable" not in t2v:
    namespace_index = t2v.find("namespace\n{")
    if namespace_index < 0:
        namespace_index = t2v.find("namespace {")
    if namespace_index < 0:
        raise SystemExit("Could not find anonymous namespace in T2VHistoryPage.cpp.")

    brace = t2v.find("{", namespace_index)
    t2v = t2v[:brace + 1] + "\n\n" + preflight_helpers + t2v[brace + 1:]

preflight_block = '''    if (!isComfyPromptApiReachable())
    {
        QMessageBox::warning(this,
                             QStringLiteral("ComfyUI Offline"),
                             comfyOfflineMessage());
        return;
    }

'''

if "ComfyUI Offline" not in t2v:
    marker = '''    const QMessageBox::StandardButton choice = QMessageBox::question(
        this,
        QStringLiteral("Submit LTX Requeue"),'''
    if marker not in t2v:
        raise SystemExit("Could not find Submit Requeue confirmation marker.")

    t2v = t2v.replace(marker, preflight_block + marker, 1)

t2v_cpp_path.write_text(t2v, encoding="utf-8")


# ----------------------------------------------------------------------
# 5) Docs + script copy.
# ----------------------------------------------------------------------

doc_path.parent.mkdir(parents=True, exist_ok=True)
doc_path.write_text(
    "# Sprint 15C Pass 27 — Comfy Startup Ownership and Accurate Runtime Health\n\n"
    "Adds ComfyUI runtime ownership to the dev launcher and blocks LTX requeue submit before confirmation when ComfyUI is offline.\n\n"
    "Changes:\n\n"
    "- Adds `scripts/dev/start_comfy.ps1`.\n"
    "- Adds `scripts/dev/stop_comfy.ps1`.\n"
    "- Updates `scripts/dev/run_ui.ps1` with `-NoComfy`, `-ComfyRoot`, and `-ComfyPort`.\n"
    "- `run_ui.ps1` now starts/adopts ComfyUI on `127.0.0.1:8188` by default.\n"
    "- Comfy startup waits for `/system_stats`, not just a listening port.\n"
    "- Comfy session metadata is written to `build/.comfy_runtime.session.json`.\n"
    "- Adopted external Comfy sessions are not stopped on exit.\n"
    "- Comfy sessions started by `run_ui.ps1` are stopped on exit.\n"
    "- `Submit Requeue` now checks Comfy reachability before showing the confirmation dialog.\n\n"
    "This separates `SpellVision worker ready` from `ComfyUI healthy`, making runtime health more accurate.\n",
    encoding="utf-8",
)

script_path.write_text(Path(__file__).read_text(encoding="utf-8") if "__file__" in globals() else "", encoding="utf-8")

print("Applied Sprint 15C Pass 27 Comfy startup ownership and runtime health preflight.")
