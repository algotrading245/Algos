# Registers the desk as two scheduled tasks of the current user (folder \AurumDesk\ in Task Scheduler).
#
#   powershell -ExecutionPolicy Bypass -File desk\install.ps1        (again to update; uninstall.ps1 removes)
#
#   Clock      every minute               python -m desk.tick: executor, triggers, schedule, runner, heartbeat
#   Watchdog   at logon and every 5 min   python -m desk.watchdog: starts the desk terminal, runs a pass when the
#                                         clock stalls, kills an agent run past its deadline
#   Dashboard  at logon, stays up         python -m desk.dashboard: http://127.0.0.1:8765, live every second
#
# Both run pythonw (no window) in the repo folder, only while this user is logged on (the terminal needs the desktop),
# with normal rights. They never touch the \Aurum\ autopilot tasks or the other MetaTrader installs.
$ErrorActionPreference = "Stop"
$Repo = Split-Path $PSScriptRoot -Parent
$folder = "\AurumDesk\"

$py = (Get-Command python -ErrorAction Stop).Source
$pyw = Join-Path (Split-Path $py) "pythonw.exe"
if (-not (Test-Path $pyw)) { $pyw = $py }
& $py -c "import MetaTrader5, psutil, pandas" 2>$null
if ($LASTEXITCODE -ne 0) { Write-Output "missing Python packages: python -m pip install MetaTrader5 psutil pandas"; exit 1 }

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 15) `
    -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

function Register($name, $triggers, $module, $text) {
    $action = New-ScheduledTaskAction -Execute $pyw -Argument "-m $module" -WorkingDirectory $Repo
    Register-ScheduledTask -TaskPath $folder -TaskName $name -Action $action -Trigger $triggers -Principal $principal `
        -Settings $settings -Description $text -Force | Out-Null
    Write-Output "registered $folder$name"
}

$every1 = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Minutes 1)
Register "Clock" $every1 "desk.tick" `
    "Aurum desk clock: one pass a minute (executor, triggers, schedule, runner, heartbeat). desk\tick.py"

$every5 = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Minutes 5)
$logon = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
Register "Watchdog" @($logon, $every5) "desk.watchdog" `
    "Aurum desk watchdog: keeps the desk terminal open and the clock alive. desk\watchdog.py"

$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 99 `
    -RestartInterval (New-TimeSpan -Minutes 1)
Register "Dashboard" $logon "desk.dashboard" `
    "Aurum desk dashboard on http://127.0.0.1:8765 (this PC only), refreshed every second. desk\dashboard.py"

Start-ScheduledTask -TaskPath $folder -TaskName "Watchdog"
Start-ScheduledTask -TaskPath $folder -TaskName "Dashboard"
Get-ScheduledTask -TaskPath $folder | ForEach-Object {
    $i = $_ | Get-ScheduledTaskInfo
    "{0,-10} {1,-8} next {2}" -f $_.TaskName, $_.State, $i.NextRunTime
}
