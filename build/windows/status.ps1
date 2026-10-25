# Shows whether the DocuPulse IDP API server is running and answering (Windows).
. (Join-Path $PSScriptRoot 'common.ps1')

$address = Get-ServerAddress
$proc = Get-ServerProcess
if (-not $proc) { Write-Host 'Not running.'; exit 3 }
if (Test-Health $address) {
    Write-Host "Running at http://$address (process $($proc.Id)), healthy."
} else {
    Write-Host "Process $($proc.Id) is running but http://$address is not answering; see $ErrFile"
    exit 1
}
