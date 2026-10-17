# Aurum keeper: keeps the PC from sleeping and FTMO-demo Terminal 16 open, so a demo EA keeps trading.
# Started at logon and every 15 minutes by the "Aurum Keeper" task; a second copy exits at once.
#
#   powershell -ExecutionPolicy Bypass -File tools\autopilot\keeper.ps1 [-Once]
#
# It never closes a terminal. It only starts Terminal 16 (without /config, so it logs in and restores its charts)
# when that terminal is not running and no hold is set (tools\autopilot\terminal.ps1 -Hold).
param([int]$Seconds = 60, [switch]$Once)
. "$PSScriptRoot\common.ps1"

$mutex = New-Object System.Threading.Mutex($false, "Local\AurumKeeper")
if (-not $mutex.WaitOne(0)) { exit 0 }

Add-Type -Namespace Aurum -Name Power -MemberDefinition @"
[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint esFlags);
"@
# ES_CONTINUOUS | ES_SYSTEM_REQUIRED: no idle sleep while this process lives (the display may still turn off).
[Aurum.Power]::SetThreadExecutionState([uint32]"0x80000001") | Out-Null
Write-Log "keeper" "keeper started (pid $PID), sleep blocked"

$lastState = ""
while ($true) {
    try {
        $hold = Get-Hold
        $t = Get-T16
        # Under a hold, Terminal 16 only runs for a tester job (run-tester.ps1 starts it with /config per run).
        if ($t) { $state = if ($hold) { "running a tester job (held by $($hold.by))" } else { "running" } }
        elseif ($hold) { $state = "held by $($hold.by) until $($hold.until)" }
        elseif (Test-DemoEA) {
            Start-Process -FilePath $T16Exe -WorkingDirectory $T16
            $state = "started"
        } else {
            # No chart has AurumFunded (a tester session can leave the charts without it): start with t16_attach.ini,
            # which opens XAUUSD M15 with AurumFunded and the demo preset. Checked only while the terminal is closed,
            # when its chart files are final, so a running EA is never attached twice.
            Start-Process -FilePath $T16Exe -WorkingDirectory $T16 -ArgumentList "/config:`"$Attach`""
            $state = "started, AurumFunded attached"
        }
        if ($state -ne $lastState) { Write-Log "keeper" "Terminal 16: $state" }
        $lastState = $state
    } catch {
        Write-Log "keeper" "error: $($_.Exception.Message)"
    }
    if ($Once) { break }
    Start-Sleep -Seconds $Seconds
}
