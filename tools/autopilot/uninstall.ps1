# Removes the Aurum scheduled tasks and stops the keeper. Terminal 16 and every other terminal are left as they are.
#
#   powershell -ExecutionPolicy Bypass -File tools\autopilot\uninstall.ps1
#
# To pause the agents without uninstalling, create logs\autopilot\PAUSE (delete it to resume).
$folder = "\Aurum\"
Get-ScheduledTask -TaskPath $folder -ErrorAction SilentlyContinue | ForEach-Object {
    Stop-ScheduledTask -TaskPath $folder -TaskName $_.TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskPath $folder -TaskName $_.TaskName -Confirm:$false
    Write-Output "removed $folder$($_.TaskName)"
}
