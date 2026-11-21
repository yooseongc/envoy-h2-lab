$labRoot = $PSScriptRoot
if (!(Test-Path -LiteralPath "$labRoot/compose.yaml")) {
    $labRoot = (Resolve-Path "$PSScriptRoot/../..").Path
}
. "$labRoot/deploy/common.ps1"
Push-Location $labRoot
try {
    Confirm-LabDirectory
    if (Test-Path app/Dockerfile) { Invoke-LabDocker compose build ui }
    New-Item -ItemType Directory -Force captures | Out-Null
    Invoke-LabDocker compose up -d --pull never --no-build
    if (Test-Path .stopped-workers.json) {
        $owned = @(Get-LabWorkers)
        foreach ($id in (Get-SavedWorkers)) {
            if ($id -in $owned) { Invoke-LabDocker start $id }
        }
        Remove-Item -LiteralPath .stopped-workers.json
    }
    foreach ($attempt in 1..60) {
        try { $state = Invoke-RestMethod http://127.0.0.1:8765/topology -TimeoutSec 2 } catch { $state = $null }
        if ($null -ne $state.clients) { Write-Output 'UI: http://127.0.0.1:8765'; return }
        Start-Sleep -Milliseconds 500
    }
    throw 'UI startup timed out. Inspect docker compose logs ui.'
} finally { Pop-Location }
