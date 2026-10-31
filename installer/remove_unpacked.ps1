# Remove trees this installer unpacked. They are not MSI components, so RemoveFiles
# will not see them. One locked file must not skip the other trees. A junction is
# removed as a link, not followed. If anything remains, fail so uninstall says so.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$left = @()
foreach ($name in @(".venv", "python-runtime", "engines")) {
    $path = Join-Path $root $name
    if (-not (Test-Path -LiteralPath $path)) { continue }
    $item = Get-Item -LiteralPath $path -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        cmd.exe /c "rmdir `"$path`""
    } else {
        Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction Continue
    }
    if (Test-Path -LiteralPath $path) { $left += $path }
}
if ($left.Count -gt 0) {
    throw ("Still present after uninstall: " + ($left -join ", "))
}
