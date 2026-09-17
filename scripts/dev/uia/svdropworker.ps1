# The doer half of svdrop.ps1. Run it, do not dot-source it.
#
# It lives in its own file because it must run on an **STA** thread: ole32!DoDragDrop refuses
# anything else, and PowerShell 7's main thread is MTA with no -STA switch left to ask for. Windows
# PowerShell 5.1 is STA by default, so svdrop.ps1 shells out to it and this is what it runs. The
# 5.1 host also compiles this C# against .NET Framework, where WinForms and System.Drawing are
# ordinary references rather than assemblies forwarded out of the default reference set.
#
# HOW THE DRAG IS STARTED, and two ways that do not work:
#
#   * Calling DoDragDrop with a hand-written IDropSource and no window of our own: the OLE loop
#     never asked QueryContinueDrag once. It is driven by button and key state changes arriving at
#     the dragging thread's own window, not by cursor movement.
#   * Jiggling the cursor to generate those events: same, for the same reason, and then it spun hot.
#
# What works is the supported shape -- a real window, a real MouseDown on it, and Control.DoDragDrop
# from inside that handler. WinForms owns the drop source and ends the drag when the button is
# released, which a background thread does after walking the cursor onto the target. That is a real
# OLE drag: Windows finds the IDropTarget under the cursor and calls DragEnter / DragOver / Drop,
# which is the path Qt registers and the path a user takes out of Explorer.
#
# Prints one line: effect=Copy means the target took the file; effect=None means nothing under the
# cursor accepted the drag, which is itself a finding.
param(
    [Parameter(Mandatory)][string]$Path,
    [Parameter(Mandatory)][int]$X,
    [Parameter(Mandatory)][int]$Y,
    [int]$HoldMs = 900,
    [string]$OverlayShot = "",
    [int]$ShotX = 0, [int]$ShotY = 0, [int]$ShotW = 0, [int]$ShotH = 0,
    [long]$Hwnd = 0
)

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

Add-Type -TypeDefinition @"
using System;
using System.Collections.Specialized;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Forms;

public class SvDragForm : Form
{
    [DllImport("user32.dll")] static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] static extern void mouse_event(uint flags, uint dx, uint dy, uint data, UIntPtr extra);
    [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] static extern bool SetProcessDPIAware();

    const uint MOUSEEVENTF_MOVE = 0x0001;
    const uint MOUSEEVENTF_LEFTDOWN = 0x0002;
    const uint MOUSEEVENTF_LEFTUP = 0x0004;

    readonly string _file, _shotPath;
    readonly int _x, _y, _holdMs, _shotX, _shotY, _shotW, _shotH;
    readonly IntPtr _target;
    public string Result = "not started";

    public SvDragForm(string file, int x, int y, int holdMs, string shotPath,
                      int shotX, int shotY, int shotW, int shotH, IntPtr target)
    {
        _file = file; _x = x; _y = y; _holdMs = holdMs; _shotPath = shotPath;
        _shotX = shotX; _shotY = shotY; _shotW = shotW; _shotH = shotH; _target = target;

        // A small real window is the drag SOURCE. It sits in the top-left corner, clear of whatever
        // is being dropped on, exactly as an Explorer window would be.
        FormBorderStyle = FormBorderStyle.None;
        StartPosition = FormStartPosition.Manual;
        Location = new Point(0, 0);
        Size = new Size(40, 40);
        ShowInTaskbar = false;
        TopMost = true;
        BackColor = Color.Black;
        Opacity = 0.01;
    }

    static void Shoot(string path, int x, int y, int w, int h)
    {
        if (string.IsNullOrEmpty(path) || w <= 0 || h <= 0) return;
        try
        {
            using (var bmp = new Bitmap(w, h))
            using (var g = Graphics.FromImage(bmp))
            {
                g.CopyFromScreen(x, y, 0, 0, bmp.Size);
                bmp.Save(path, ImageFormat.Png);
            }
        }
        catch { }
    }

    protected override void OnShown(EventArgs e)
    {
        base.OnShown(e);
        // Press the button on OUR window, never on the target: a button-down delivered to the widget
        // being dropped on is a click it never received in the real gesture.
        SetCursorPos(Left + Width / 2, Top + Height / 2);
        Application.DoEvents();
        mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, UIntPtr.Zero);
    }

    protected override void OnMouseDown(MouseEventArgs e)
    {
        base.OnMouseDown(e);

        var files = new StringCollection();
        files.Add(_file);
        var data = new DataObject();
        data.SetFileDropList(files);

        int sx = Left + Width / 2, sy = Top + Height / 2;
        var mover = new Thread(delegate() {
            try
            {
                if (_target != IntPtr.Zero) SetForegroundWindow(_target);
                // Walk, so the window under the cursor gets DragEnter and a run of DragOver rather
                // than one teleport.
                for (int i = 1; i <= 16; i++)
                {
                    SetCursorPos(sx + (_x - sx) * i / 16, sy + (_y - sy) * i / 16);
                    mouse_event(MOUSEEVENTF_MOVE, 0, 0, 0, UIntPtr.Zero);
                    Thread.Sleep(20);
                }
                // Sit still while the drag-enter overlay is on screen. No screenshot taken after the
                // drop can show that state.
                Thread.Sleep(_holdMs);
                Shoot(_shotPath, _shotX, _shotY, _shotW, _shotH);
            }
            finally
            {
                // Releasing is what ends the drag. Always, whatever happened above: a left button
                // left down is a wedged desktop.
                mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, UIntPtr.Zero);
            }
        });
        mover.IsBackground = true;
        mover.Start();

        DragDropEffects effect = DoDragDrop(data, DragDropEffects.Copy);
        mover.Join(3000);
        Result = "effect=" + effect.ToString();
        Close();
    }

    public static string Run(string file, int x, int y, int holdMs, string shotPath,
                             int shotX, int shotY, int shotW, int shotH, IntPtr target)
    {
        SetProcessDPIAware();
        Application.EnableVisualStyles();
        var f = new SvDragForm(file, x, y, holdMs, shotPath, shotX, shotY, shotW, shotH, target);
        Application.Run(f);
        return f.Result;
    }
}
"@ -ReferencedAssemblies System.Windows.Forms, System.Drawing

$full = (Resolve-Path $Path).Path
[SvDragForm]::Run($full, $X, $Y, $HoldMs, $OverlayShot, $ShotX, $ShotY, $ShotW, $ShotH, [IntPtr]$Hwnd)
