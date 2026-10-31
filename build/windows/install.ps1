# Installs IDP on Windows: Python environment, packages, and the web UI build.
#   build\windows\install.bat         (or: powershell -ExecutionPolicy Bypass -File build\windows\install.ps1)
# Uses build\wheels\ if present (offline), else the internet. Needs Python 3.11+, 3.12 recommended ("py" launcher or python.exe).
# Building the UI needs Node.js 22 or 24 (an even, LTS release), unless frontend\dist is already there.
. (Join-Path $PSScriptRoot 'common.ps1')

if (-not (Test-Path $Py)) {
    # Prefer Python 3.12 (the version the offline package's wheels are built for), then 3.11, then the default
    $launcher = if (Get-Command py -ErrorAction SilentlyContinue) {
        $v = @('-3.12', '-3.11', '-3') | Where-Object { & py $_ -c "import sys" 2>$null; $LASTEXITCODE -eq 0 } | Select-Object -First 1
        @('py', $v)
    } elseif (Get-Command python -ErrorAction SilentlyContinue) { @('python') } else { $null }
    if (-not $launcher) { throw 'Python 3.11 or newer (3.12 recommended) is required. Install it from python.org (or copy the installer to this server).' }
    & $launcher[0] $launcher[1..9] -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 or newer (3.12 recommended) is required; 3.9 and 3.10 no longer get security fixes.' }
    Write-Host "Creating the Python environment in $Venv"
    & $launcher[0] $launcher[1..9] -m venv $Venv
}

$wheels = Join-Path $Root 'build\wheels'
$source = @('--disable-pip-version-check')
if (Test-Path $wheels) {
    Write-Host "Installing packages offline from $wheels"
    $source += @('--no-index', '--find-links', $wheels)
}
& $Py -m pip install @source -r (Join-Path $Backend 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Package installation failed.' }

# Servers do not need OpenCV's GUI parts: use the headless build (same module)
if ($OnWindows) {
    & $Py -m pip uninstall -y opencv-python 2>$null | Out-Null
    & $Py -m pip install @source opencv-python-headless
}

if (Test-Path (Join-Path $Root 'frontend\dist\index.html')) {
    Write-Host 'Web UI already built (frontend\dist).'
} elseif (Test-NodeOk) {
    Write-Host 'Building the web UI'
    Push-Location (Join-Path $Root 'frontend')
    try { npm ci; npm run build } finally { Pop-Location }
} elseif (Get-Command node -ErrorAction SilentlyContinue) {
    Write-Host "Note: Node.js $(node -v) cannot build the UI; it needs version 22 or 24. Install one of those, or build the UI on another machine and copy frontend\dist here."
} else {
    Write-Host 'Note: frontend\dist is missing and Node.js is not installed. Build the UI on another machine and copy frontend\dist here.'
}

Write-Host ''
Write-Host 'Installed. Review backend\config\server.ini and database.ini (created on first start), then run:'
Write-Host '  build\windows\start.bat'
