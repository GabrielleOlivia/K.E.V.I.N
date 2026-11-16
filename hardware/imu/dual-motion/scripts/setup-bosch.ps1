# Retrieves Bosch's official BHI360 SensorAPI and firmware; requires internet and Git.
# Run from the PlatformIO project directory:
#   powershell -ExecutionPolicy Bypass -File .\scripts\setup-bosch.ps1
$ErrorActionPreference = 'Stop'
$project = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$vendor = Join-Path $project 'lib\BoschBHI360\src'
$firmware = Join-Path $project 'include\bhi360'
$tempDir = Join-Path ([System.IO.Path]::GetTempPath()) ('kevin-bosch-bhi360-' + [guid]::NewGuid().ToString('N'))
try {
    Write-Host 'Downloading official Bosch BHI360 SensorAPI v2.3.1 ...'
    git clone --depth 1 --branch v2.3.1 'https://github.com/boschsensortec/BHI360_SensorAPI.git' $tempDir
    if ($LASTEXITCODE -ne 0) { throw 'git clone failed; check connectivity/Git installation.' }
    New-Item -ItemType Directory -Force -Path $vendor, $firmware | Out-Null
    Copy-Item (Join-Path $tempDir 'source\*.h') $vendor -Force
    $sources = @('bhi360.c','bhi360_hif.c','bhi360_event_data.c','bhi360_parse.c','bhi360_virtual_sensor_conf_param.c')
    foreach ($source in $sources) { Copy-Item (Join-Path $tempDir "source\$source") $vendor -Force }
    Copy-Item (Join-Path $tempDir 'firmware\bhi360\Bosch_Shuttle3_BHI360_bsxsam.fw.h') $firmware -Force
    Copy-Item (Join-Path $tempDir 'LICENSE') (Join-Path $project 'lib\BoschBHI360\LICENSE') -Force
    Write-Host 'Bosch SDK and firmware installed. Open this project in PlatformIO and BUILD before uploading.' -ForegroundColor Green
}
finally {
    if (Test-Path $tempDir) { Remove-Item $tempDir -Recurse -Force }
}
