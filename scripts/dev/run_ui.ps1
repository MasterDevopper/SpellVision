$ErrorActionPreference = "Stop"

.\.venv\Scripts\Activate.ps1
python -m py_compile python\worker_service.py python\worker_client.py

$env:CMAKE_PREFIX_PATH = "C:\Qt\6.10.2\msvc2022_64"
$env:Qt6_DIR = "C:\Qt\6.10.2\msvc2022_64\lib\cmake\Qt6"

cmake -S . -B build -G "Visual Studio 18 2026" -A x64 -DQt6_DIR="C:\Qt\6.10.2\msvc2022_64\lib\cmake\Qt6"
cmake --build build --config Debug

if (-not (Test-Path .\build\Debug\SpellVision.exe)) {
    throw "Build succeeded but SpellVision.exe was not found."
}

.\build\Debug\SpellVision.exe