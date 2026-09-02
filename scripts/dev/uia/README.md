# Driving the real UI

Two PowerShell helpers that drive the built `SpellVision.exe` through Windows UI Automation and
capture what a user would see. They exist because the 2026-09-02 live pass found six defects that
the rigs and the responsive matrix had passed: the canvas cap converging on a cold 48x86 label, an
error pill cut mid-word, a queue count that read a finished job as pending, and a stuck Generate
on two of the four generation pages.

    . .\scripts\dev\uia\svdrive.ps1          # dot-source (svui.ps1 comes with it)
    Set-SvState -State Restore -W 1776 -H 1059
    Select-SvRail T2I
    Invoke-SvGenerate -Prompt "a lighthouse at dusk" -TimeoutSec 300
    Save-SvMatrix -Prefix t2i               # Restore / Full / HalfW / HalfH screenshots

`Get-SvElements` lists the accessible tree (Qt exposes objectName as AutomationId, button text as
Name); `Save-SvShot` / `Save-SvCrop` capture the window at 1:1; `Get-SvStatusText` reads the bottom
telemetry bar, which is the only status that changes during a render.

Lesson written into `Set-SvState`: PowerShell variable names are case-insensitive. A local `$h`
overwrote the `$H` height parameter with the window handle, Windows clamped that to its maximum
track height, and an hour went into a "bug" where the app grew to 1460px. Locals are `$hwnd`.
