# Removes the desk's scheduled tasks (\AurumDesk\Clock, \AurumDesk\Watchdog and \AurumDesk\Dashboard). It does not close positions, stop
# the desk terminal or delete any file: halt the desk first with `python -m desk.cli kill "why"` if positions are open.
#
#   powershell -ExecutionPolicy Bypass -File desk\uninstall.ps1
$folder = "\AurumDesk\"
foreach ($name in "Clock", "Watchdog", "Dashboard") {
    if (Get-ScheduledTask -TaskPath $folder -TaskName $name -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskPath $folder -TaskName $name -Confirm:$false
        Write-Output "removed $folder$name"
    }
}
