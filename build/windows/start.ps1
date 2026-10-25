# Starts the DocuPulse IDP API server in the background (Windows).
# Settings: backend\config\server.ini and database.ini. Logs: backend\storage\logs\server.log / server.err.log
. (Join-Path $PSScriptRoot 'common.ps1')

if (-not (Test-Path $Py)) { throw 'Not installed yet: run build\windows\install.bat first.' }
$running = Get-ServerProcess
if ($running) { Write-Host "Already running (process $($running.Id))."; exit 0 }

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$address = Get-ServerAddress
$startArgs = @{ FilePath = $Py; ArgumentList = 'run.py'; WorkingDirectory = $Backend; PassThru = $true
                RedirectStandardOutput = $LogFile; RedirectStandardError = $ErrFile }
if ($OnWindows) { $startArgs['WindowStyle'] = 'Hidden' }
$proc = Start-Process @startArgs
Set-Content -Path $PidFile -Value $proc.Id

for ($i = 0; $i -lt 60; $i++) {
    if (Test-Health $address) { Write-Host "DocuPulse is running at http://$address (process $($proc.Id))."; exit 0 }
    if ($proc.HasExited) {
        Write-Host 'The server stopped during start-up. Last log lines:'
        Get-Content $ErrFile -Tail 20
        Remove-Item $PidFile -ErrorAction SilentlyContinue
        exit 1
    }
    Start-Sleep -Seconds 1
}
Write-Host "Started (process $($proc.Id)) but http://$address is not answering yet; see $ErrFile"
