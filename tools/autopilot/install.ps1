# Registers the Aurum autopilot as scheduled tasks of the current user (folder \Aurum\ in Task Scheduler).
#
#   powershell -ExecutionPolicy Bypass -File tools\autopilot\install.ps1        (again to update; uninstall.ps1 removes)
#
#   Aurum Keeper        at logon and every 15 min    keeps the PC awake and Terminal 16 open (keeper.ps1)
#   Aurum Monitor       Mon-Fri 23:15                monitor agent (haiku): demo check-in
#   Aurum Relay         every 5 min                  the agent team (relay.ps1): each agent hands over to the next,
#                                                    which starts at once (no gap inside a cycle); a 30 min break
#                                                    between cycles; tester and scanner steps are scripts (keeper)
#
# The relay replaces the fixed-time Orchestrator, Tester and Researcher tasks of the first install; they are removed.
#
# The tasks run only while this user is logged on (Terminal 16 needs the desktop), with normal rights, and do not wake
# the PC. A missed start runs as soon as the PC is available again.
. "$PSScriptRoot\common.ps1"
$folder = "\Aurum\"

function Action($script, $arguments) {
    New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory $Repo `
        -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$PSScriptRoot\$script`" $arguments"
}
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

function Register($name, $triggers, $action, $text) {
    Register-ScheduledTask -TaskPath $folder -TaskName $name -Action $action -Trigger $triggers -Principal $principal `
        -Settings $settings -Description $text -Force | Out-Null
    Write-Output "registered $folder$name"
}

$every15 = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Minutes 15)
Register "Aurum Keeper" @((New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"), $every15) `
    (Action "keeper.ps1" "") "Keeps the PC awake and FTMO-demo Terminal 16 open, and runs the tester and scanner scripts every minute (tools\autopilot\keeper.ps1)."

Register "Aurum Monitor" (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At 23:15) `
    (Action "run-agent.ps1" "-Role monitor") "Monitor agent: daily demo check-in into docs\demo_log.md (its model comes from tools\autopilot\router.json)."

$every5 = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Minutes 5)
Register "Aurum Relay" $every5 (Action "relay.ps1" "") `
    "Agent relay: the chain researcher, miner, scanner, orchestrator, tester, fidelity hands over to itself; provider and models come from tools\autopilot\router.json (tools\autopilot\relay.ps1)."

foreach ($old in "Aurum Orchestrator", "Aurum Tester", "Aurum Researcher") {
    if (Get-ScheduledTask -TaskPath $folder -TaskName $old -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskPath $folder -TaskName $old -Confirm:$false
        Write-Output "removed $folder$old (the relay runs this agent now)"
    }
}

Start-ScheduledTask -TaskPath $folder -TaskName "Aurum Keeper"
Get-ScheduledTask -TaskPath $folder | ForEach-Object {
    $i = $_ | Get-ScheduledTaskInfo
    "{0,-20} {1,-8} next {2}" -f $_.TaskName, $_.State, $i.NextRunTime
}
