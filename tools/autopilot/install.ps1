# Registers the Aurum autopilot as scheduled tasks of the current user (folder \Aurum\ in Task Scheduler).
#
#   powershell -ExecutionPolicy Bypass -File tools\autopilot\install.ps1        (again to update; uninstall.ps1 removes)
#
#   Aurum Keeper        at logon and every 15 min    keeps the PC awake and Terminal 16 open (keeper.ps1)
#   Aurum Monitor       Mon-Fri 23:15                monitor agent (haiku): demo check-in
#   Aurum Orchestrator  daily 07:30 and 19:30        orchestrator (opus): one pipeline task per run
#   Aurum Tester        Sat and Sun hourly           tester agent (sonnet), only when a tester job needs it
#   Aurum Researcher    Sunday 10:00                 researcher agent (haiku): new ideas
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
    (Action "keeper.ps1" "") "Keeps the PC awake and FTMO-demo Terminal 16 open (tools\autopilot\keeper.ps1)."

Register "Aurum Monitor" (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At 23:15) `
    (Action "run-agent.ps1" "-Role monitor") "Monitor agent (haiku): daily demo check-in into docs\demo_log.md."

Register "Aurum Orchestrator" @((New-ScheduledTaskTrigger -Daily -At 07:30), (New-ScheduledTaskTrigger -Daily -At 19:30)) `
    (Action "run-agent.ps1" "-Role orchestrator") "Orchestrator (opus): one pipeline task per run, commits and pushes."

$tester = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Saturday, Sunday -At 00:30
$tester.Repetition = (New-ScheduledTaskTrigger -Once -At 00:30 -RepetitionInterval (New-TimeSpan -Hours 1) `
    -RepetitionDuration (New-TimeSpan -Hours 23)).Repetition
Register "Aurum Tester" $tester (Action "run-agent.ps1" "-Role tester -IfWork") `
    "Tester agent (sonnet): runs docs\autopilot\queue.json jobs on Terminal 16 in the weekend window."

Register "Aurum Researcher" (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 10:00) `
    (Action "run-agent.ps1" "-Role researcher") "Researcher agent (haiku): up to 5 new ideas into docs\ideas\."

Start-ScheduledTask -TaskPath $folder -TaskName "Aurum Keeper"
Get-ScheduledTask -TaskPath $folder | ForEach-Object {
    $i = $_ | Get-ScheduledTaskInfo
    "{0,-20} {1,-8} next {2}" -f $_.TaskName, $_.State, $i.NextRunTime
}
