# Creates a desktop shortcut that launches Time Tracker without a terminal window
$appDir   = "D:\time-tracker"
$pywFile  = "$appDir\TimeTracker.pyw"
$iconHint = "$appDir\TimeTracker.pyw"   # Windows will use the pythonw icon

# Locate pythonw.exe next to the active python.exe
$python = (Get-Command python.exe -ErrorAction Stop).Source
$pythonw = $python -replace 'python\.exe$', 'pythonw.exe'
if (-not (Test-Path $pythonw)) { $pythonw = $python }

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = "$desktop\Time Tracker.lnk"

$shell     = New-Object -ComObject WScript.Shell
$shortcut  = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath      = $pythonw
$shortcut.Arguments       = "`"$pywFile`""
$shortcut.WorkingDirectory = $appDir
$shortcut.Description     = "Time Tracker - PB&J Strategic Accounting"
$shortcut.Save()

Write-Host ""
Write-Host "Shortcut created on your Desktop: Time Tracker.lnk"
Write-Host "Double-click it to launch the app - no terminal window."
