# Captures T2I and Home for each (preset, material) pair, one app launch per pair, and restores the
# persisted preset afterwards. Preset indices: 0 Arcane Glass, 1 Obsidian Studio, 2 Neon Forge,
# 3 Ivory Holograph, 4 Ember. Material: 0 Refined Glass, 1 Matte Instrument, 2 Hybrid.
param(
    [string]$Prefix = "themes",
    [int[]]$Presets = @(0, 3),
    [int[]]$Materials = @(0, 1, 2)
)
$root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
. (Join-Path $PSScriptRoot "svdrive.ps1")
$key = "HKCU:\Software\DarkDuck\SpellVision\appearance"
$orig = Get-ItemProperty $key
try {
    foreach ($p in $Presets) {
        foreach ($m in $Materials) {
            Set-ItemProperty $key -Name themePreset -Value ([int]$p)
            Set-ItemProperty $key -Name surfaceStyle -Value ([int]$m)
            $proc = Start-Process -FilePath (Join-Path $root "build\Debug\SpellVision.exe") -WorkingDirectory $root -PassThru
            $deadline = (Get-Date).AddSeconds(45); $hwnd = 0
            while ((Get-Date) -lt $deadline) { try { $hwnd = Get-SvHwnd } catch { $hwnd = 0 }; if ($hwnd) { break }; Start-Sleep -Milliseconds 500 }
            if (-not $hwnd) { Write-Warning "no window for preset $p material $m"; Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue; continue }
            Start-Sleep -Seconds 4
            Set-SvState -State Restore -W 1600 -H 1000 | Out-Null; Start-Sleep -Milliseconds 1500
            Select-SvRail T2I | Out-Null; Start-Sleep -Milliseconds 1500; Save-SvShot -Name "$Prefix-p$p-m$m-t2i" | Out-Null
            Select-SvRail Home | Out-Null; Start-Sleep -Milliseconds 2200; Save-SvShot -Name "$Prefix-p$p-m$m-home" | Out-Null
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue; Start-Sleep -Milliseconds 1500
        }
    }
} finally {
    Set-ItemProperty $key -Name themePreset -Value ([int]$orig.themePreset)
    Set-ItemProperty $key -Name surfaceStyle -Value ([int]$orig.surfaceStyle)
    "restored themePreset=$($orig.themePreset) surfaceStyle=$($orig.surfaceStyle)"
}
