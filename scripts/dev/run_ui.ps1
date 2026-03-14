$ErrorActionPreference = "Stop"

Set-Location (Resolve-Path "$PSScriptRoot\..\..")

Write-Host "==> Activating venv" -ForegroundColor Cyan
& .\.venv\Scripts\Activate.ps1

Write-Host "==> Python syntax check" -ForegroundColor Cyan
python -m py_compile python\worker_service.py python\worker_client.py

Write-Host "==> Configuring Qt/CMake environment" -ForegroundColor Cyan
$env:CMAKE_PREFIX_PATH = "C:\Qt\6.10.2\msvc2022_64"
$env:Qt6_DIR = "C:\Qt\6.10.2\msvc2022_64\lib\cmake\Qt6"

Write-Host "==> Configuring build" -ForegroundColor Cyan
cmake -S . -B build -G "Visual Studio 18 2026" -A x64 -DQt6_DIR="$env:Qt6_DIR"

Write-Host "==> Building SpellVision" -ForegroundColor Cyan
cmake --build build --config Debug

$exe = ".\build\Debug\SpellVision.exe"
if (-not (Test-Path $exe)) {
    throw "Build completed but $exe was not found."
}

Write-Host "==> Launching UI" -ForegroundColor Green
& $exe