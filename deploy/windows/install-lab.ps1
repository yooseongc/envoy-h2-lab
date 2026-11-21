$labRoot = $PSScriptRoot
if (!(Test-Path -LiteralPath "$labRoot/compose.yaml")) {
    $labRoot = (Resolve-Path "$PSScriptRoot/../..").Path
}
. "$labRoot/deploy/common.ps1"
Push-Location $labRoot
try {
    $manifest = @{}
    foreach ($line in (Get-Content images.manifest)) {
        $key, $value = $line -split ' ', 2
        $manifest[$key] = $value
    }
    if ((Get-FileHash images.tar.gz -Algorithm SHA256).Hash -ne $manifest.sha256) { throw 'Archive checksum mismatch' }
    $platform = Invoke-LabDocker version --format '{{.Server.Os}}/{{.Server.Arch}}'
    if ($platform -ne $manifest.platform) { throw "Archive requires $($manifest.platform); engine is $platform" }
    Invoke-LabDocker compose version
    Invoke-LabDocker load --input images.tar.gz
    foreach ($tag in $manifest.Keys) {
        if ($tag -in @('sha256', 'platform')) { continue }
        if ((Invoke-LabDocker image inspect --format '{{.Id}}' $tag) -ne $manifest[$tag]) {
            throw "Image ID mismatch: $tag"
        }
    }
    New-Item -ItemType Directory -Force captures | Out-Null
} finally { Pop-Location }
