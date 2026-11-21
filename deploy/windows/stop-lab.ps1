$labRoot = $PSScriptRoot
if (!(Test-Path -LiteralPath "$labRoot/compose.yaml")) {
    $labRoot = (Resolve-Path "$PSScriptRoot/../..").Path
}
. "$labRoot/deploy/common.ps1"
Push-Location $labRoot
try {
    Confirm-LabDirectory
    $running = @(Get-LabWorkers -Running)
    if ($running.Count) {
        $ids = @( (@(Get-SavedWorkers) + $running) | Sort-Object -Unique )
        ConvertTo-Json -InputObject $ids -Compress | Set-Content .stopped-workers.tmp -Encoding ascii
        Move-Item -Force -LiteralPath .stopped-workers.tmp -Destination .stopped-workers.json
    }
    Invoke-LabDocker compose stop
    if ($running.Count) { Invoke-LabDocker stop @running }
} finally { Pop-Location }
