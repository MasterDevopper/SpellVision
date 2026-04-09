param(
    [string]$QtRoot = "",
    [switch]$NoBackend,
    [switch]$NoTranslations,
    [switch]$FastDeploy
)

$ErrorActionPreference = "Stop"

function Resolve-ProjectRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

function Resolve-PythonExe {
    param([string]$ProjectRoot)

    $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return $venvPython
    }

    return "python"
}

function Resolve-QtRoot {
    param([string]$RequestedQtRoot)

    if ($RequestedQtRoot) {
        $resolved = (Resolve-Path $RequestedQtRoot).Path
        if (-not (Test-Path (Join-Path $resolved "lib\cmake\Qt6\Qt6Config.cmake"))) {
            throw "Qt6Config.cmake not found under requested QtRoot: $resolved"
        }
        return $resolved
    }

    $candidates = @(
        $env:QTDIR,
        "C:\Qt\6.10.2\msvc2022_64",
        "C:\Qt\6.8.2\msvc2022_64",
        "C:\Qt\6.7.3\msvc2022_64"
    ) | Where-Object { $_ -and $_.Trim() -ne "" }

    foreach ($candidate in $candidates) {
        try {
            $resolved = (Resolve-Path $candidate).Path
            if (Test-Path (Join-Path $resolved "lib\cmake\Qt6\Qt6Config.cmake")) {
                return $resolved
            }
        }
        catch {
        }
    }

    throw "Unable to resolve a valid Qt installation. Pass -QtRoot `"C:\Qt\6.10.2\msvc2022_64`" or set QTDIR."
}

function Set-QtEnvironment {
    param([string]$ResolvedQtRoot)

    $qt6Dir = Join-Path $ResolvedQtRoot "lib\cmake\Qt6"
    $env:QTDIR = $ResolvedQtRoot
    $env:Qt6_DIR = $qt6Dir

    if ($env:CMAKE_PREFIX_PATH) {
        if ($env:CMAKE_PREFIX_PATH -notmatch [regex]::Escape($ResolvedQtRoot)) {
            $env:CMAKE_PREFIX_PATH = "$ResolvedQtRoot;$($env:CMAKE_PREFIX_PATH)"
        }
    }
    else {
        $env:CMAKE_PREFIX_PATH = $ResolvedQtRoot
    }

    $qtBin = Join-Path $ResolvedQtRoot "bin"
    if ($env:Path -notmatch [regex]::Escape($qtBin)) {
        $env:Path = "$qtBin;$($env:Path)"
    }
}

function Invoke-PythonSyntaxCheck {
    param(
        [string]$PythonExe,
        [string]$ProjectRoot
    )

    Write-Host "==> Python syntax check"
    $files = @(
        (Join-Path $ProjectRoot "python\worker_service.py"),
        (Join-Path $ProjectRoot "python\worker_client.py")
    ) | Where-Object { Test-Path $_ }

    foreach ($file in $files) {
        & $PythonExe -m py_compile $file
        if ($LASTEXITCODE -ne 0) {
            throw "Python syntax check failed for $file"
        }
    }
}

$projectRoot = Resolve-ProjectRoot
$pythonExe = Resolve-PythonExe -ProjectRoot $projectRoot
$resolvedQtRoot = $null
$backendSessionAcquired = $false

try {
    Write-Host "==> Activating venv"
    $activateScript = Join-Path $projectRoot ".venv\Scripts\Activate.ps1"
    if (Test-Path $activateScript) {
        . $activateScript
    }

    Invoke-PythonSyntaxCheck -PythonExe $pythonExe -ProjectRoot $projectRoot

    Write-Host "==> Configuring Qt/CMake environment"
    $resolvedQtRoot = Resolve-QtRoot -RequestedQtRoot $QtRoot
    Set-QtEnvironment -ResolvedQtRoot $resolvedQtRoot

    $buildDir = Join-Path $projectRoot "build"

    Write-Host "==> Configuring build"
    $cmakeArgs = @(
        "-S", $projectRoot,
        "-B", $buildDir,
        "-G", "Visual Studio 18 2026",
        "-A", "x64",
        "-DCMAKE_PREFIX_PATH=$env:CMAKE_PREFIX_PATH",
        "-DQt6_DIR=$env:Qt6_DIR"
    )

    if ($NoTranslations) {
        $cmakeArgs += "-DSPELLVISION_DEPLOY_NO_TRANSLATIONS=ON"
    }

    if ($FastDeploy) {
        $cmakeArgs += "-DSPELLVISION_DEPLOY_FAST_DEV=ON"
    }

    & cmake @cmakeArgs
    if ($LASTEXITCODE -ne 0) {
        throw "CMake configure failed with exit code $LASTEXITCODE"
    }

    Write-Host "==> Building SpellVision"
    & cmake --build $buildDir --config Debug
    if ($LASTEXITCODE -ne 0) {
        throw "Build failed with exit code $LASTEXITCODE"
    }

    $exe = Join-Path $buildDir "Debug\SpellVision.exe"
    if (-not (Test-Path $exe)) {
        throw "Build completed but $exe was not found."
    }

    if (-not $NoBackend) {
        Write-Host "==> Ensuring backend session"
        & (Join-Path $PSScriptRoot "start_backend.ps1") -ProjectRoot $projectRoot -PythonExe $pythonExe
        if ($LASTEXITCODE -ne 0) {
            throw "Backend start failed."
        }
        $backendSessionAcquired = $true
    }

    Write-Host "==> Launching UI"
    & $exe
}
finally {
    if ($backendSessionAcquired) {
        Write-Host "==> Stopping backend session"
        try {
            & (Join-Path $PSScriptRoot "stop_backend.ps1") -ProjectRoot $projectRoot
        }
        catch {
            Write-Warning "Failed to stop backend session: $($_.Exception.Message)"
        }
    }
}
