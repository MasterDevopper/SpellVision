# Helper for driving the SpellVision window: geometry, screenshots, UI Automation.
# Dot-source:  . .\svui.ps1
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

if (-not ("SvNative" -as [type])) {
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class SvNative {
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT r);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr hWnd, IntPtr after, int x, int y, int cx, int cy, uint flags);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int cmd);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint flags, uint dx, uint dy, uint data, UIntPtr extra);
    [DllImport("user32.dll")] public static extern bool IsZoomed(IntPtr hWnd);
}
"@
}
[void][SvNative]::SetProcessDPIAware()

$script:ShotDir = Join-Path $PSScriptRoot "shots"
New-Item -ItemType Directory -Force -Path $script:ShotDir | Out-Null

function Get-SvHwnd {
    $p = Get-Process -Name SpellVision -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if (-not $p) { throw "SpellVision window not found" }
    return $p.MainWindowHandle
}

function Get-SvRect {
    $hwnd = Get-SvHwnd
    $r = New-Object SvNative+RECT
    [void][SvNative]::GetWindowRect($hwnd, [ref]$r)
    [pscustomobject]@{ X=$r.Left; Y=$r.Top; W=($r.Right-$r.Left); H=($r.Bottom-$r.Top); Maximized=[SvNative]::IsZoomed($hwnd) }
}

function Set-SvState {
    param([ValidateSet("Full","Restore","HalfW","HalfH","Custom")] [string]$State, [int]$X=100, [int]$Y=60, [int]$W=1600, [int]$H=1000)
    $hwnd = Get-SvHwnd
    $work = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
    # PowerShell variable names are case-insensitive: a local `$h` here silently overwrote the `$H`
    # height parameter with the window handle, and Windows clamped that to its max track height
    # (1460 on a 1440px screen). Locals are `$hwnd`; only un-maximize when actually maximized.
    $target = $null
    switch ($State) {
        "Full"    { if (-not [SvNative]::IsZoomed($hwnd)) { [void][SvNative]::SetWindowPos($hwnd, [IntPtr]::Zero, $work.X+100, $work.Y+60, 1600, 1000, 0x0014); Start-Sleep -Milliseconds 300 }; [void][SvNative]::ShowWindow($hwnd, 3) }
        "Restore" { $target = @($X, $Y, $W, $H) }
        "HalfW"   { $target = @($work.X, $work.Y, [int]($work.Width/2), $work.Height) }
        "HalfH"   { $target = @($work.X, $work.Y, $work.Width, [int]($work.Height/2)) }
        "Custom"  { $target = @($X, $Y, $W, $H) }
    }
    if ($target) {
        if ([SvNative]::IsZoomed($hwnd)) { [void][SvNative]::ShowWindow($hwnd, 9); Start-Sleep -Milliseconds 400 }
        [void][SvNative]::SetWindowPos($hwnd, [IntPtr]::Zero, $target[0], $target[1], $target[2], $target[3], 0x0014)
        Start-Sleep -Milliseconds 300
    }
    [void][SvNative]::SetForegroundWindow($hwnd)
    Start-Sleep -Milliseconds 700
    if ($target) {
        $r = Get-SvRect
        if ($r.W -ne $target[2] -or $r.H -ne $target[3]) {
            Write-Warning ("window came back {0}x{1} for a {2}x{3} request; re-applying" -f $r.W, $r.H, $target[2], $target[3])
            [void][SvNative]::SetWindowPos($hwnd, [IntPtr]::Zero, $target[0], $target[1], $target[2], $target[3], 0x0014)
            Start-Sleep -Milliseconds 500
        }
    }
    Get-SvRect
}

function Save-SvShot {
    param([Parameter(Mandatory)][string]$Name)
    $r = Get-SvRect
    $bmp = New-Object System.Drawing.Bitmap($r.W, $r.H)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($r.X, $r.Y, 0, 0, $bmp.Size)
    $g.Dispose()
    $path = Join-Path $script:ShotDir ("{0}.png" -f $Name)
    $bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
    return $path
}

function Get-SvRoot {
    $hwnd = Get-SvHwnd
    return [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
}

function Get-SvElements {
    # All descendants, optionally filtered; returns Name/AutomationId/ControlType/Rect/Offscreen.
    param([string]$NameLike="", [string]$IdLike="", [string]$Type="", [switch]$OnScreenOnly)
    $root = Get-SvRoot
    $all = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
    $out = foreach ($e in $all) {
        $c = $e.Current
        if ($NameLike -and ($c.Name -notlike $NameLike)) { continue }
        if ($IdLike -and ($c.AutomationId -notlike $IdLike)) { continue }
        if ($Type -and ($c.ControlType.ProgrammaticName -ne "ControlType.$Type")) { continue }
        if ($OnScreenOnly -and $c.IsOffscreen) { continue }
        $b = $c.BoundingRectangle
        if ([double]::IsInfinity($b.X) -or [double]::IsNaN($b.X)) { if ($OnScreenOnly) { continue }; $bx=-1;$by=-1;$bw=0;$bh=0 } else { $bx=[int]$b.X;$by=[int]$b.Y;$bw=[int]$b.Width;$bh=[int]$b.Height }
        if ($OnScreenOnly -and ($bw -le 0 -or $bh -le 0)) { continue }
        [pscustomobject]@{
            Type=$c.ControlType.ProgrammaticName -replace '^ControlType\.',''
            Name=$c.Name; Id=$c.AutomationId; Class=$c.ClassName
            X=$bx; Y=$by; W=$bw; H=$bh
            Off=$c.IsOffscreen; Enabled=$c.IsEnabled; Element=$e
        }
    }
    return $out
}

function Invoke-SvElement {
    param([Parameter(Mandatory)]$Item)
    $e = $Item.Element
    $p = $null
    if ($e.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$p)) { $p.Invoke(); return "invoked" }
    if ($e.TryGetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern, [ref]$p)) { $p.Toggle(); return "toggled" }
    if ($e.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$p)) { $p.Select(); return "selected" }
    Invoke-SvClick ([int]($Item.X + $Item.W/2)) ([int]($Item.Y + $Item.H/2)); return "clicked"
}

function Invoke-SvClick {
    param([int]$X, [int]$Y)
    [void][SvNative]::SetForegroundWindow((Get-SvHwnd))
    [void][SvNative]::SetCursorPos($X, $Y)
    Start-Sleep -Milliseconds 80
    [SvNative]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 40
    [SvNative]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 200
}

function Set-SvText {
    # ValuePattern if offered; else click into it, select all, paste from clipboard.
    param([Parameter(Mandatory)]$Item, [Parameter(Mandatory)][string]$Text)
    $p = $null
    if ($Item.Element.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$p) -and -not $p.Current.IsReadOnly) {
        $p.SetValue($Text); return "value"
    }
    Invoke-SvClick ([int]($Item.X + 20)) ([int]($Item.Y + 12))
    [System.Windows.Forms.Clipboard]::SetText($Text)
    [System.Windows.Forms.SendKeys]::SendWait("^a")
    Start-Sleep -Milliseconds 60
    [System.Windows.Forms.SendKeys]::SendWait("^v")
    Start-Sleep -Milliseconds 150
    return "pasted"
}

function Get-SvText {
    param([Parameter(Mandatory)]$Item)
    $p = $null
    if ($Item.Element.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$p)) { return $p.Current.Value }
    if ($Item.Element.TryGetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern, [ref]$p)) { return $p.DocumentRange.GetText(-1) }
    return $Item.Name
}
