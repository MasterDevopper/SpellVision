# What does ComfyUI's DynamicVRAM actually do when the card is smaller?
#
# --reserve-vram N is passed straight to comfy_aimdo as simple_vram_headroom, i.e. "keep N GB free".
# On a 32 GB card that is a usable EMULATION of a smaller card: reserve 16 and the engine has ~16 to
# work with. It is not identical to owning a 16 GB card (host RAM and PCIe are unchanged), but it is
# the question the product actually faces -- can the heaviest path complete when VRAM is scarce --
# measured on hardware we have rather than assumed from hardware we do not.
param([double[]]$Reserve = @(0, 16, 22, 26), [int]$W = 768, [int]$H = 512, [int]$F = 49)

$ErrorActionPreference = "Stop"
$comfy   = "C:\sv_comfynext_v034\ComfyUI"
$py      = "C:\sv_comfynext_v034\.venv\Scripts\python.exe"
$repo    = "C:\Users\xXste\Code_Projects\SpellVision"
$probe   = "$repo\scripts\dev\measure_video_upscale_render.py"
$results = @()

function Stop-Comfy {
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like "*sv_comfynext_v034*main.py*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue }
    Start-Sleep -Seconds 6
}

function Start-Comfy([string[]]$Extra) {
    $args = @("$comfy\main.py", "--listen", "127.0.0.1", "--port", "8188", "--use-sage-attention") + $Extra
    $env:PYTHONUTF8 = "1"; $env:PYTHONIOENCODING = "utf-8"
    $log = "$env:TEMP\comfy_headroom.log"
    Start-Process -FilePath $py -ArgumentList $args -WorkingDirectory $comfy `
        -RedirectStandardError $log -RedirectStandardOutput "$env:TEMP\comfy_headroom.out" -WindowStyle Hidden
    for ($i = 0; $i -lt 120; $i++) {
        try { Invoke-RestMethod -Uri "http://127.0.0.1:8188/system_stats" -TimeoutSec 3 | Out-Null; return $log } catch { Start-Sleep -Seconds 2 }
    }
    throw "ComfyUI did not come up"
}

$seed = 80100
foreach ($r in $Reserve) {
    Stop-Comfy
    $extra = if ($r -gt 0) { @("--reserve-vram", "$r") } else { @() }
    Write-Output "=== reserve-vram $r GB (budget ~$([math]::Round(31.8 - $r,1)) GB) @ ${W}x${H}x${F}f ==="
    $log = Start-Comfy $extra
    $seed++
    # Built as a literal. ConvertTo-Json silently DROPPED the trailing $null and flattened the
    # nested array, so the probe received a 4- or 5-element row and died on unpack -- a serializer
    # quietly changing the shape of the thing being measured.
    $case = '[["hdr' + $r + '",' + $W + ',' + $H + ',' + $F + ',' + $seed + ',null]]'

    # Did the flag take? aimdo reports the PHYSICAL card either way, so the banner cannot answer it.
    # Free VRAM at idle can: reserving N means the engine will not climb into that N.
    $stats = Invoke-RestMethod -Uri "http://127.0.0.1:8188/system_stats" -TimeoutSec 10
    $freeGb = [math]::Round($stats.devices[0].vram_free / 1GB, 2)
    Write-Output "    idle free: $freeGb GB"

    $out = & "$repo\.venv\Scripts\python.exe" $probe $case 2>&1 | Out-String
    Write-Output $out.Trim()
    $aimdo = Select-String -Path $log -Pattern "inited for GPU|headroom|DynamicVRAM" -EA SilentlyContinue |
             Select-Object -Last 3 | ForEach-Object { $_.Line.Trim() }
    if ($aimdo) { Write-Output ("    aimdo: " + ($aimdo -join " | ")) }
    $results += [pscustomobject]@{ reserve = $r; output = $out.Trim() }
}

Stop-Comfy
Write-Output "=== restoring the default launch ==="
& "$repo\scripts\dev\start_comfy.ps1" | Select-Object -Last 2
