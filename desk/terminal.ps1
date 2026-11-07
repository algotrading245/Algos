# Sets up the desk's own MetaTrader 5 terminal, portable, in C:\MetaTrader 5 - Desk (desk\config.json terminal.path),
# and puts an "Aurum Desk Terminal" shortcut on the desktop.
#
#   powershell -ExecutionPolicy Bypass -File desk\terminal.ps1 [-From "C:\MetaTrader 5 - Tester"] [-Start]
#
# It copies only the program files (terminal64.exe, MetaEditor64.exe, metatester64.exe, the icon and Sounds) from an
# existing MT5 install, reading it and never writing to it: no Config, Profiles, bases or logs, so no account or
# setting comes across. The new terminal starts with no account; the owner logs the demo in.
param([string]$From = "C:\MetaTrader 5 - Tester", [switch]$Start)
$ErrorActionPreference = "Stop"
$exe = (Get-Content (Join-Path $PSScriptRoot "config.json") -Raw | ConvertFrom-Json).terminal.path
$dest = Split-Path $exe -Parent

if (-not (Test-Path $exe)) {
    if (-not (Test-Path (Join-Path $From "terminal64.exe"))) {
        Write-Output "no MT5 install at $From. Install MetaTrader 5 from https://www.metatrader5.com/en/download into"
        Write-Output "$dest (installer > Settings > installation folder), or pass -From with another MT5 folder."
        exit 1
    }
    New-Item -ItemType Directory -Force $dest | Out-Null
    foreach ($f in "terminal64.exe", "MetaEditor64.exe", "metatester64.exe", "Terminal.ico") {
        $src = Join-Path $From $f
        if (Test-Path $src) { Copy-Item $src $dest }
    }
    if (Test-Path (Join-Path $From "Sounds")) { Copy-Item (Join-Path $From "Sounds") $dest -Recurse }
    Write-Output "desk terminal copied to $dest"
} else {
    Write-Output "desk terminal already at $dest"
}

$lnk = Join-Path ([Environment]::GetFolderPath("Desktop")) "Aurum Desk Terminal.lnk"
$sh = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
$sh.TargetPath = $exe
$sh.Arguments = "/portable"
$sh.WorkingDirectory = $dest
$ico = Join-Path $dest "Terminal.ico"
if (Test-Path $ico) { $sh.IconLocation = $ico }
$sh.Description = "Aurum desk: the demo terminal the desk trades (portable)"
$sh.Save()
Write-Output "shortcut: $lnk"

if ($Start) { Start-Process -FilePath $exe -ArgumentList "/portable" -WorkingDirectory $dest }
