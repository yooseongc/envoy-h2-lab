$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    python deploy/lab.py stop
    if ($LASTEXITCODE -ne 0) { throw "Lab stop failed." }
} finally { Pop-Location }
