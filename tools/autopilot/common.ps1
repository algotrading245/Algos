# Shared paths and the tester window for the autopilot scripts. Dot-source it: . "$PSScriptRoot\common.ps1"
#
# Terminal 16 (FTMO demo) runs both the demo EA and the Strategy Tester. MT5 ignores /config while the terminal is
# open, so tester jobs only run in the weekend window, when the markets of the demo legs are shut.

$Repo     = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$LogDir   = Join-Path $Repo "logs\autopilot"
$HoldFile = Join-Path $LogDir "hold-terminal"
$Pause    = Join-Path $LogDir "PAUSE"
$T16      = "C:\Program Files\MetaTrader 5 - 16"
$T16Exe   = Join-Path $T16 "terminal64.exe"
New-Item -ItemType Directory -Force $LogDir | Out-Null

function Write-Log([string]$Name, [string]$Text) {
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Text
    Add-Content -Path (Join-Path $LogDir "$(Get-Date -Format yyyy-MM-dd)_$Name.log") -Value $line -Encoding UTF8
}

# Weekend window, local time: Saturday 00:00 to Sunday 18:00 (FTMO reopens Sunday evening, server = local + 1h).
function Get-WindowEnd([datetime]$Now = (Get-Date)) {
    $d = $Now.Date
    switch ($Now.DayOfWeek) {
        "Saturday" { return $d.AddDays(1).AddHours(18) }
        "Sunday"   { if ($Now.Hour -lt 18) { return $d.AddHours(18) } }
    }
    return $null
}
function Test-Window { return [bool](Get-WindowEnd) }

# Terminal 16's own process; the other installs (live and other firms' accounts) are never matched.
function Get-T16 {
    Get-CimInstance Win32_Process -Filter "Name='terminal64.exe'" |
        Where-Object { $_.ExecutablePath -and ($_.ExecutablePath -ieq $T16Exe) }
}

# A hold keeps the keeper from restarting Terminal 16. Expired or unreadable holds are removed.
function Get-Hold {
    if (-not (Test-Path $HoldFile)) { return $null }
    try { $h = Get-Content $HoldFile -Raw | ConvertFrom-Json; $until = [datetime]$h.until } catch { $until = Get-Date 0 }
    if ($until -le (Get-Date)) { Remove-Item $HoldFile -Force; return $null }
    return $h
}
