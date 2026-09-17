# Drop a real file on the real window, through the real OLE drag-and-drop path.
#
# UI Automation cannot do this: there is no pattern for "drag a file from Explorer onto that
# widget". WM_DROPFILES cannot do it either -- Qt registers an IDropTarget with RegisterDragDrop and
# never sees the legacy message, so a WM_DROPFILES "drop" would prove nothing about the path a user
# actually takes. This does what Explorer does: build a FileDrop data object, put the cursor over
# the target point, and call ole32!DoDragDrop. Windows then finds the IDropTarget under the cursor
# and calls DragEnter / DragOver / Drop on it, which is the path W4 built.
#
#     . .\scripts\dev\uia\svdrive.ps1
#     . .\scripts\dev\uia\svdrop.ps1
#     Invoke-SvFileDrop -Path D:\drops\asteral.json -X 900 -Y 40 -OverlayShot t6_overlay
#
# The work happens in svdropworker.ps1 under Windows PowerShell 5.1, because DoDragDrop requires an
# STA thread and PowerShell 7 has neither an STA main thread nor a -STA switch to ask for one.

if (-not ("SvZOrder" -as [type])) {
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class SvZOrder {
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint f);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
}
"@
}

function Set-SvTopMost {
    <#
      Pins (or unpins) the SpellVision window above everything else. A capture pass is worthless if
      another window is sitting over the half of the shell being photographed -- the first run of
      this pass photographed a browser.
    #>
    param([bool]$On = $true)
    $hwnd = Get-SvHwnd
    $after = if ($On) { [IntPtr](-1) } else { [IntPtr](-2) }   # HWND_TOPMOST / HWND_NOTOPMOST
    [void][SvZOrder]::SetWindowPos($hwnd, $after, 0, 0, 0, 0, 0x0013)  # NOSIZE|NOMOVE|SHOWWINDOW
    [void][SvZOrder]::SetForegroundWindow($hwnd)
    Start-Sleep -Milliseconds 200
}

function Invoke-SvFileDrop {
    <#
      Drops $Path on the SpellVision window at screen point ($X,$Y). $OverlayShot, when given, is a
      PNG written DURING the drag -- the drag-enter state, which no screenshot taken afterwards can
      show. Returns the DoDragDrop result: effect=Copy means the target took the file;
      effect=None means nothing under the cursor accepted the drag.
    #>
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][int]$X,
        [Parameter(Mandatory)][int]$Y,
        [int]$HoldMs = 900,
        [string]$OverlayShot = "",
        [int]$TimeoutSec = 45
    )
    $full = (Resolve-Path $Path).Path
    $hwnd = 0; $sx = 0; $sy = 0; $sw = 0; $sh = 0
    try {
        $r = Get-SvRect
        $hwnd = [long](Get-SvHwnd)
        $sx = $r.X; $sy = $r.Y; $sw = $r.W; $sh = $r.H
    } catch { }

    $shot = ""
    if ($OverlayShot) {
        $shot = if ([System.IO.Path]::IsPathRooted($OverlayShot)) { $OverlayShot }
                else { Join-Path (Join-Path $PSScriptRoot "shots") ("{0}.png" -f $OverlayShot) }
        New-Item -ItemType Directory -Force -Path (Split-Path $shot) | Out-Null
    }

    $worker = Join-Path $PSScriptRoot "svdropworker.ps1"
    $ps51 = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
    $argv = @(
        "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-File", ('"{0}"' -f $worker),
        "-Path", ('"{0}"' -f $full), "-X", $X, "-Y", $Y, "-HoldMs", $HoldMs,
        "-ShotX", $sx, "-ShotY", $sy, "-ShotW", $sw, "-ShotH", $sh, "-Hwnd", $hwnd
    )
    if ($shot) { $argv += @("-OverlayShot", ('"{0}"' -f $shot)) }

    # Detached, with a deadline. A drop whose handler opens a MODAL dialog does not return from
    # IDropTarget::Drop until the dialog is dismissed, and the dismissing has to happen from this
    # session -- so this must not be the thing that blocks it.
    $stdout = [System.IO.Path]::GetTempFileName()
    $proc = Start-Process -FilePath $ps51 -ArgumentList $argv -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput $stdout
    if (-not $proc.WaitForExit($TimeoutSec * 1000)) {
        return "PENDING pid=$($proc.Id) shot=$shot (still inside the drop handler -- a modal dialog is probably up)"
    }
    $out = Get-Content $stdout -ErrorAction SilentlyContinue
    Remove-Item $stdout -ErrorAction SilentlyContinue
    return (($out | Where-Object { $_ } | Select-Object -Last 1))
}
