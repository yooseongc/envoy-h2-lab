$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if (-not (Test-Path -LiteralPath 'images.json')) {
        docker compose build ui
        if ($LASTEXITCODE -ne 0) { throw "Development build failed." }
    }
    python deploy/lab.py start
    if ($LASTEXITCODE -ne 0) { throw "Lab start failed." }
} finally { Pop-Location }
