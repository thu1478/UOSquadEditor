$ErrorActionPreference = "Stop"
$ROOT = Split-Path $PSScriptRoot -Parent
$Editor = Join-Path $ROOT "Tools\mission_editor"

# Don't inherit Pages/CI base paths into local vite.
Remove-Item Env:VITE_BASE -ErrorAction SilentlyContinue
Remove-Item Env:VITE_STATIC -ErrorAction SilentlyContinue

Push-Location $Editor
try {
    if (-not (Test-Path (Join-Path $Editor "node_modules"))) {
        Write-Host "Installing dependencies (first run)..." -ForegroundColor Cyan
        npm.cmd install
    }
    Write-Host "Starting UO Tools hub..." -ForegroundColor Green
    Write-Host "  Hub:    http://localhost:5173/" -ForegroundColor DarkGray
    Write-Host "  Editor: http://localhost:5173/editor/" -ForegroundColor DarkGray
    npm.cmd run dev
}
finally {
    Pop-Location
}
