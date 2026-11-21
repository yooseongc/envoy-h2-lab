$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    python deploy/lab.py install
    if ($LASTEXITCODE -ne 0) { throw "Lab install failed." }
} finally { Pop-Location }
