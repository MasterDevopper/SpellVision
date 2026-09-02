# Drives generations through the real SpellVision UI. Dot-source after svui.ps1.
. (Join-Path $PSScriptRoot "svui.ps1")

function Get-SvPage {
    # Which MainPageStack page is currently showing (by AutomationId segment).
    $els = Get-SvElements -IdLike "*MainPageStack.*" -OnScreenOnly
    $seg = $els | ForEach-Object { ($_.Id -split '\.')[3] } | Group-Object | Sort-Object Count -Descending | Select-Object -First 1
    return $seg.Name
}

function Select-SvRail {
    param([Parameter(Mandatory)][string]$Name)
    $btn = Get-SvElements -Type CheckBox -IdLike "*SideRailColumn.SideRailButton" -OnScreenOnly | Where-Object { $_.Name -eq $Name } | Select-Object -First 1
    if (-not $btn) { throw "rail button '$Name' not on screen" }
    Invoke-SvClick ([int]($btn.X + $btn.W/2)) ([int]($btn.Y + $btn.H/2))
    Start-Sleep -Milliseconds 900
}

function Set-SvDisclosure {
    param([ValidateSet("Simple","Advanced")][string]$Mode)
    $btn = Get-SvElements -Type CheckBox -IdLike "*TitleBarModeButton" -OnScreenOnly | Where-Object { $_.Name -eq $Mode } | Select-Object -First 1
    if (-not $btn) { throw "mode toggle '$Mode' not found" }
    Invoke-SvClick ([int]($btn.X + $btn.W/2)) ([int]($btn.Y + $btn.H/2))
    Start-Sleep -Milliseconds 900
}

function Get-SvStatusText {
    # Bottom telemetry bar: state (Idle/Running…), Queue: N (outstanding since the tally fix), and
    # the readiness/error pill in the action row. The inspector's "Ready to generate" never changes
    # during a run, which is what made the first wait loop run out its clock.
    $els = Get-SvElements -Type Text
    $bar = $els | Where-Object { $_.Id -like "*BottomStateLabel" -or $_.Id -like "*BottomQueueLabel" -or $_.Id -like "*BottomEtaLabel" }
    $pill = $els | Where-Object { $_.Id -like "*MainPageStack.ImageGenerationPage*CanvasCard*" -and -not $_.Off -and $_.Name -match '⚠|Error|error|fail' } | Select-Object -First 1
    $parts = @($bar | ForEach-Object { $_.Name.Trim() } | Where-Object { $_ })
    if ($pill) { $parts += $pill.Name }
    return ($parts -join " | ")
}

function Get-SvGenerateButton {
    return Get-SvElements -Type Button -IdLike "*MainPageStack.ImageGenerationPage*PrimaryActionButton" -OnScreenOnly | Select-Object -First 1
}

function Invoke-SvGenerate {
    param([string]$Prompt = "", [int]$TimeoutSec = 300)
    if ($Prompt) {
        $edit = Get-SvElements -Type Edit -IdLike "*MainPageStack.ImageGenerationPage*PromptCard.QTextEdit" -OnScreenOnly | Sort-Object Y | Select-Object -First 1
        if (-not $edit) { throw "prompt edit not on screen" }
        $how = Set-SvText -Item $edit -Text $Prompt
        Write-Host "prompt set via $how"
    }
    # Foreground first, then re-measure: the window has been seen to grow on activation.
    [void][SvNative]::SetForegroundWindow((Get-SvHwnd))
    Start-Sleep -Milliseconds 900
    $gen = Get-SvGenerateButton
    if (-not $gen) { throw "Generate button not on screen" }
    $work = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
    if (($gen.Y + $gen.H) -gt $work.Bottom) { throw ("Generate button bottom {0} is below the work area {1}; window is {2}" -f ($gen.Y+$gen.H), $work.Bottom, ((Get-SvRect) | ForEach-Object { "$($_.W)x$($_.H)" })) }
    $before = Get-SvStatusText
    Invoke-SvClick ([int]($gen.X + $gen.W/2)) ([int]($gen.Y + $gen.H/2))
    $sw = [Diagnostics.Stopwatch]::StartNew()
    Start-Sleep -Seconds 3
    $last = ""
    while ($sw.Elapsed.TotalSeconds -lt $TimeoutSec) {
        $gen = Get-SvGenerateButton
        $status = Get-SvStatusText
        if ($status -ne $last) { Write-Host ("[{0,5:N0}s] {1}" -f $sw.Elapsed.TotalSeconds, $status); $last = $status }
        $busy = ($status -match 'Queue: [1-9]|Running|Generat|Render|Prepar|Starting|Queued|Loading|%') -or ($gen -and -not $gen.Enabled)
        if (-not $busy -and $sw.Elapsed.TotalSeconds -gt 6) { break }
        Start-Sleep -Seconds 2
    }
    return [pscustomobject]@{ Seconds=[int]$sw.Elapsed.TotalSeconds; Status=$last; Before=$before }
}

function Save-SvMatrix {
    param([Parameter(Mandatory)][string]$Prefix, [string[]]$States = @("Restore","Full","HalfW","HalfH"), [int]$SettleMs = 1200)
    $out = @()
    foreach ($s in $States) {
        $r = Set-SvState -State $s
        Start-Sleep -Milliseconds $SettleMs
        $p = Save-SvShot -Name "$Prefix-$s"
        $out += [pscustomobject]@{ State=$s; W=$r.W; H=$r.H; Path=$p }
    }
    return $out
}

function Save-SvCrop {
    # Crop of the current window at 1:1, window-relative coordinates.
    param([Parameter(Mandatory)][string]$Name, [int]$X, [int]$Y, [int]$W, [int]$H)
    $r = Get-SvRect
    $bmp = New-Object System.Drawing.Bitmap($W, $H)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($r.X + $X, $r.Y + $Y, 0, 0, $bmp.Size)
    $g.Dispose()
    $path = Join-Path $script:ShotDir ("{0}.png" -f $Name)
    $bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
    return $path
}
