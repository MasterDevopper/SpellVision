# The Canvas inspector's expand-on-demand, driven LIVE and captured either side of it: collapsed,
# pushed open by a tab glyph, and collapsed again by the same glyph. A vs C is the reversibility of
# the peek in pixels; A vs B is that the push actually happened.
. "$PSScriptRoot\svdrive.ps1"

$key = "HKCU:\Software\DarkDuck\SpellVision\ui"
Set-ItemProperty -Path $key -Name "shellLayout" -Value 1 -Type DWord

Stop-Process -Name SpellVision -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Start-Process -FilePath (Join-Path $PSScriptRoot "..\..\..\build\Debug\SpellVision.exe")
Start-Sleep -Seconds 14
Set-SvState -State Restore -X 100 -Y 60 -W 1600 -H 1000 | Out-Null
Start-Sleep -Seconds 2
Select-SvRail T2I
Start-Sleep -Seconds 3

Save-SvShot -Name "t7-peek-a-collapsed"

$tab = Get-SvElements -IdLike "*InspectorTab" -OnScreenOnly | Select-Object -First 1
if (-not $tab) { throw "no inspector tab glyph on screen" }
Write-Output ("glyph at {0},{1} {2}x{3} name='{4}'" -f $tab.X, $tab.Y, $tab.W, $tab.H, $tab.Name)
$cx = [int]($tab.X + $tab.W/2); $cy = [int]($tab.Y + $tab.H/2)

Invoke-SvClick $cx $cy
Start-Sleep -Milliseconds 1200
Save-SvShot -Name "t7-peek-b-open"

# The column moved, so the glyph moved with it: ask again rather than clicking where it used to be.
# NOT matched by Name -- the collapsed tile's accessible name IS its glyph and the expanded one is
# the word, so a name match fails exactly when the expand worked. Same ordinal instead.
$tab2 = Get-SvElements -IdLike "*InspectorTab" -OnScreenOnly | Select-Object -First 1
if (-not $tab2) { throw "the tab strip vanished when the column opened" }
Write-Output ("open glyph at {0},{1} name='{2}'" -f $tab2.X, $tab2.Y, $tab2.Name)
Invoke-SvClick ([int]($tab2.X + $tab2.W/2)) ([int]($tab2.Y + $tab2.H/2))
Start-Sleep -Milliseconds 1200
Save-SvShot -Name "t7-peek-c-collapsed-again"
