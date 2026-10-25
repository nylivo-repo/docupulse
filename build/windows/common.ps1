# Shared paths and helpers for the Windows scripts (Windows PowerShell 5.1 or PowerShell 7). Not run directly.
$ErrorActionPreference = 'Stop'

$Root     = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Backend  = Join-Path $Root 'backend'
$Venv     = Join-Path $Root 'venv'
# Windows puts venv executables in Scripts\; PowerShell 7 on Mac/Linux (used for testing) in bin/
$OnWindows = ($PSVersionTable.PSVersion.Major -lt 6) -or $IsWindows
$Py       = if ($OnWindows) { Join-Path $Venv 'Scripts\python.exe' } else { Join-Path $Venv 'bin/python' }
$PidFile  = Join-Path $Backend 'storage\server.pid'
$LogDir   = Join-Path $Backend 'storage\logs'
$LogFile  = Join-Path $LogDir 'server.log'
$ErrFile  = Join-Path $LogDir 'server.err.log'

function Get-ServerAddress {
    # Host and port as the server will use them (config\server.ini, overridden by environment variables)
    Push-Location $Backend
    try {
        $addr = & $Py -c "from app.core.config import settings; h = settings.HOST; print(('127.0.0.1' if h in ('0.0.0.0', '::') else h) + ':' + str(settings.PORT))"
    } finally { Pop-Location }
    return $addr.Trim()
}

function Get-ServerProcess {
    if (-not (Test-Path $PidFile)) { return $null }
    $procId = [int](Get-Content $PidFile -Raw)
    return Get-Process -Id $procId -ErrorAction SilentlyContinue
}

function Test-Health([string]$Address) {
    try {
        $r = Invoke-WebRequest -Uri "http://$Address/api/health" -UseBasicParsing -TimeoutSec 3
        return $r.StatusCode -eq 200
    } catch { return $false }
}

# The web UI (Angular) builds with Node.js 22 or 24 and newer even (LTS) releases only
function Test-NodeOk {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { return $false }
    $major = [int]((node -p "process.versions.node.split('.')[0]") 2>$null)
    return ($major -ge 22) -and ($major % 2 -eq 0)
}
