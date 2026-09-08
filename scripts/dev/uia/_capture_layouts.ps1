# Task 7 capture pass: T2I in each of the three shell layouts, one preset, one session.
# The layout is read from QSettings at construction (nothing in the shipped app can change it live
# until the Settings card lands), so each capture is its own launch of the same binary.
#
# IT WRITES ui/shellLayout AND DOES NOT PUT IT BACK. Whoever runs it owns restoring the key -- it was
# ABSENT on this machine before the pass, so the restore is a Remove-ItemProperty, not a zero.
param([Parameter(Mandatory)][string]$Prefix, [Parameter(Mandatory)][int]$LayoutIndex)

. "$PSScriptRoot\svdrive.ps1"

$key = "HKCU:\Software\DarkDuck\SpellVision\ui"
New-Item -Path $key -Force | Out-Null
Set-ItemProperty -Path $key -Name "shellLayout" -Value $LayoutIndex -Type DWord

Stop-Process -Name SpellVision -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Start-Process -FilePath (Join-Path $PSScriptRoot "..\..\..\build\Debug\SpellVision.exe")
Start-Sleep -Seconds 14

Set-SvState -State Restore -X 100 -Y 60 -W 1600 -H 1000 | Out-Null
Start-Sleep -Seconds 2
Select-SvRail T2I
Start-Sleep -Seconds 3
$page = Get-SvPage
Write-Output ("page = {0}" -f $page)
Save-SvShot -Name $Prefix
