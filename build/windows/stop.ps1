# Stops the IDP API server started with start.ps1 / start.bat (Windows).
. (Join-Path $PSScriptRoot 'common.ps1')

$proc = Get-ServerProcess
if (-not $proc) {
    Write-Host 'Not running.'
    Remove-Item $PidFile -ErrorAction SilentlyContinue
    exit 0
}
Stop-Process -Id $proc.Id
for ($i = 0; $i -lt 15; $i++) {
    if (-not (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue)) { break }
    Start-Sleep -Seconds 1
}
if (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue) { Stop-Process -Id $proc.Id -Force }
Remove-Item $PidFile -ErrorAction SilentlyContinue
Write-Host 'Stopped.'
