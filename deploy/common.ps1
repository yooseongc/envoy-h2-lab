$ErrorActionPreference = 'Stop'
function Invoke-LabDocker {
    & docker @args
    if ($LASTEXITCODE -ne 0) { throw "Docker command failed: docker $args" }
}
function Confirm-LabDirectory {
    $containers = Invoke-LabDocker ps -aq --filter label=com.docker.compose.project=envoy-h2-lab --filter label=com.docker.compose.service=ui
    foreach ($id in $containers) {
        $labels = (Invoke-LabDocker inspect --format '{{json .Config.Labels}}' $id) | ConvertFrom-Json
        $directory = $labels.'com.docker.compose.project.working_dir'
        if ($directory -and [IO.Path]::GetFullPath($directory) -ne (Get-Location).Path) {
            throw "Another installation owns this project: $directory"
        }
    }
}
function Get-LabWorkers([switch]$Running) {
    $flag = if ($Running) { '-q' } else { '-aq' }
    Invoke-LabDocker ps $flag --no-trunc --filter label=lab.project=envoy-h2-lab
}
function Get-SavedWorkers {
    if (Test-Path .stopped-workers.json) {
        Get-Content .stopped-workers.json -Raw | ConvertFrom-Json | ForEach-Object { $_ }
    }
}
