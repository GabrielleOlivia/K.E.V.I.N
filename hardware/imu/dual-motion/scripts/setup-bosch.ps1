# Install a minimal subset of Bosch BHI360 SensorAPI v2.3.1 for the
# K.E.V.I.N. SAMD21 dual-IMU proof of concept (Windows PowerShell 5.1 compatible).
# Run from hardware/imu/dual-motion:
#   powershell -ExecutionPolicy Bypass -File .\scripts\setup-bosch.ps1
$ErrorActionPreference = 'Stop'
$project = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$vendor = Join-Path $project 'lib\BoschBHI360\src'
$firmware = Join-Path $project 'include\bhi360'
$tempDir = Join-Path ([System.IO.Path]::GetTempPath()) ('kevin-bosch-bhi360-' + [guid]::NewGuid().ToString('N'))

try {
    Write-Host 'Downloading official Bosch BHI360 SensorAPI v2.3.1 ...'
    git clone --depth 1 --branch v2.3.1 'https://github.com/boschsensortec/BHI360_SensorAPI.git' $tempDir
    if ($LASTEXITCODE -ne 0) { throw 'git clone failed; check Git and your network connection.' }

    New-Item -ItemType Directory -Force -Path $vendor, $firmware | Out-Null
    Copy-Item (Join-Path $tempDir 'source\*.h') $vendor -Force

    # Do not copy bhi360_parse.c: it is an OPTIONAL Bosch example/debug printer
    # that depends on the Bosch COINES host SDK (coines.h, verbose.h). Our
    # sketch uses its own quaternion callback and needs only these core C files.
    $sources = @(
        'bhi360.c',
        'bhi360_hif.c',
        'bhi360_event_data.c',
        'bhi360_virtual_sensor_conf_param.c'
    )
    foreach ($source in $sources) {
        Copy-Item (Join-Path $tempDir "source\$source") $vendor -Force
    }

    # Remove stale copy from first setup (otherwise PlatformIO still compiles it).
    $oldParser = Join-Path $vendor 'bhi360_parse.c'
    if (Test-Path $oldParser) { Remove-Item $oldParser -Force }

    # Bosch's header defines three C99 designated-initializer arrays with gaps.
    # GCC 9's C++ front end cannot compile those arrays. They are human-readable
    # lookup tables, used by the C parsing tools, not our C++ application.
    # Preserve them for C sources; omit their private declarations for C++.
    $defsPath = Join-Path $vendor 'bhi360_event_data_defs.h'
    $defs = [System.IO.File]::ReadAllText($defsPath)
    $arrays = @(
        'bhi360_event_data_multi_tap_string_out',
        'bhi360_event_data_head_gesture_string_out',
        'bhi360_event_data_wrist_gesture_detect_output'
    )
    foreach ($array in $arrays) {
        $pattern = 'static\s+const\s+char\s*\*\s*const\s+' + [regex]::Escape($array) + '\[\]\s*=\s*\{[\s\S]*?\};'
        $regex = New-Object System.Text.RegularExpressions.Regex($pattern)
        if ($regex.Matches($defs).Count -ne 1) {
            throw "Cannot safely adapt Bosch header: expected exactly one declaration for $array"
        }
        $replacement = "#ifndef __cplusplus`r`n" + '$0' + "`r`n#endif"
        $defs = $regex.Replace($defs, $replacement, 1)
    }
    [System.IO.File]::WriteAllText($defsPath, $defs)

    Copy-Item (Join-Path $tempDir 'firmware\bhi360\Bosch_Shuttle3_BHI360_bsxsam.fw.h') $firmware -Force
    Copy-Item (Join-Path $tempDir 'LICENSE') (Join-Path $project 'lib\BoschBHI360\LICENSE') -Force

    Write-Host 'Bosch core SDK and firmware installed. COINES-only parser excluded; C++ compatibility adjusted.' -ForegroundColor Green
    Write-Host 'Run PlatformIO: Build. Do NOT upload until build and memory usage are checked.'
}
finally {
    if (Test-Path $tempDir) { Remove-Item $tempDir -Recurse -Force }
}
