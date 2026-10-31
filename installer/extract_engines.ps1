# Extract the engine archives this MSI carries. Run from the install directory.
# Refuse a zip entry that would write outside that directory. The cabinets are
# unsigned, so a swapped part must not become a write anywhere SYSTEM can reach.
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$root = [System.IO.Path]::GetFullPath((Split-Path -Parent $MyInvocation.MyCommand.Path))
if (-not $root.EndsWith([System.IO.Path]::DirectorySeparatorChar)) {
    $root = $root + [System.IO.Path]::DirectorySeparatorChar
}

function Test-SafeEntry([string]$name) {
    if ([string]::IsNullOrWhiteSpace($name)) { return $false }
    $normalized = $name.Replace([char]92, [char]47).TrimStart([char]47)
    if ($normalized.Contains(':') -or $normalized.StartsWith('/')) { return $false }
    $allowed = $normalized.StartsWith('.venv/') -or $normalized.StartsWith('python-runtime/') -or $normalized.StartsWith('engines/')
    if (-not $allowed) { return $false }
    foreach ($part in $normalized.Split([char]47)) {
        if ($part -eq '..' -or $part -eq '') { return $false }
    }
    return $true
}

$parts = Get-ChildItem -Path (Join-Path $root "parts") -Filter "engines-*.zip" | Sort-Object Name
if (-not $parts) { throw "SpellVision engine archives were not installed." }

foreach ($part in $parts) {
    $zip = [System.IO.Compression.ZipFile]::OpenRead($part.FullName)
    try {
        foreach ($entry in $zip.Entries) {
            if (-not (Test-SafeEntry $entry.FullName)) {
                throw "Refused engine archive entry: $($entry.FullName)"
            }
            $dest = [System.IO.Path]::GetFullPath((Join-Path $root $entry.FullName))
            if (-not $dest.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "Refused engine archive path: $($entry.FullName)"
            }
            if ($entry.FullName.EndsWith('/') -or $entry.FullName.EndsWith('\')) {
                New-Item -ItemType Directory -Force -Path $dest | Out-Null
                continue
            }
            $parent = Split-Path -Parent $dest
            if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
            [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $dest, $true)
        }
    } finally {
        $zip.Dispose()
    }
}

# The app cannot rewrite these files under Program Files. This action is the one
# that can. Scrub the build-machine path out of the command line.
$runtime = Join-Path $root.TrimEnd([char]92) "python-runtime"
$python = Join-Path $runtime "python.exe"
if (-not (Test-Path -LiteralPath $python)) { throw "Bundled Python was not unpacked." }
foreach ($rel in @(".venv\pyvenv.cfg", "engines\.venv\pyvenv.cfg")) {
    $cfg = Join-Path $root.TrimEnd([char]92) $rel
    if (-not (Test-Path -LiteralPath $cfg)) { continue }
    $venv = Split-Path -Parent $cfg
    $rewritten = foreach ($line in (Get-Content -LiteralPath $cfg)) {
        if ($line -match '^\s*home\s*=') { "home = $runtime" }
        elseif ($line -match '^\s*executable\s*=') { "executable = $python" }
        elseif ($line -match '^\s*command\s*=') { "command = $python -m venv $venv" }
        else { $line }
    }
    Set-Content -LiteralPath $cfg -Value $rewritten -Encoding ascii
}
