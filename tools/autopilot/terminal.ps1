# Hold, release or show Terminal 16 for Strategy Tester jobs.
#
#   ... terminal.ps1 -Status
#   ... terminal.ps1 -Hold                  autopilot: weekend window only, held until the window ends (10 h at most)
#   ... terminal.ps1 -Hold -By owner -Hours 6   owner: any time, e.g. to keep the terminal shut for maintenance
#   ... terminal.ps1 -Release
#
# -Hold writes the hold, then closes Terminal 16 gracefully (as if its window were closed) and waits for it. It never
# kills the terminal: if it does not close in 2 minutes the hold stays and the script says so.
param([switch]$Hold, [switch]$Release, [switch]$Status, [string]$By = "autopilot", [double]$Hours = 6)
. "$PSScriptRoot\common.ps1"

function Show {
    $t = Get-T16; $h = Get-Hold; $end = Get-WindowEnd
    [pscustomobject]@{
        terminal16 = if ($t) { "running" } else { "closed" }
        hold       = if ($h) { "$($h.by) until $($h.until)" } else { "none" }
        window     = if ($end) { "open until $($end.ToString('yyyy-MM-dd HH:mm'))" } else { "closed (Saturday 00:00 to Sunday 18:00)" }
        paused     = Test-Path $Pause
    } | ConvertTo-Json
}

if ($Release) {
    if (Test-Path $HoldFile) { Remove-Item $HoldFile -Force; Write-Log "keeper" "hold released" }
    Show; exit 0
}

if ($Hold) {
    if ($By -eq "autopilot") {
        $end = Get-WindowEnd
        if (-not $end) { Write-Output "refused: outside the weekend window, the demo needs the terminal"; exit 2 }
        $until = @($end, (Get-Date).AddHours(10)) | Sort-Object | Select-Object -First 1
    } else {
        $until = (Get-Date).AddHours($Hours)
    }
    @{ by = $By; since = (Get-Date).ToString("s"); until = $until.ToString("s") } | ConvertTo-Json |
        Set-Content $HoldFile -Encoding UTF8
    Write-Log "keeper" "hold set by $By until $($until.ToString('s'))"
    foreach ($t in @(Get-T16)) {
        $p = Get-Process -Id $t.ProcessId -ErrorAction SilentlyContinue
        if ($p) { $p.CloseMainWindow() | Out-Null; $p.WaitForExit(120000) | Out-Null }
    }
    if (Get-T16) { Write-Output "Terminal 16 did not close within 2 minutes; hold kept, nothing killed"; Show; exit 3 }
    Write-Log "keeper" "Terminal 16 closed for the hold"
    Show; exit 0
}

Show
