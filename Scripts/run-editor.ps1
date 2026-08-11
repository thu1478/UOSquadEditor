$ErrorActionPreference = "Stop"
$ROOT = Split-Path $PSScriptRoot -Parent
$Editor = Join-Path $ROOT "Tools\mission_editor"

Push-Location $Editor
try {
    if (-not (Test-Path (Join-Path $Editor "node_modules"))) {
        Write-Host "Installing dependencies (first run)..." -ForegroundColor Cyan
        npm.cmd install
    }
    Write-Host "Starting Mission Squad Editor..." -ForegroundColor Green
    npm.cmd run dev
}
finally {
    Pop-Location
}
