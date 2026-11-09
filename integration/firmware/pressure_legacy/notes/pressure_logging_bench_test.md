# Pressure logging bench test

This test checks the logging and calibration changes using the existing SensorHub, pressure module and syringe. The next respiratory experiment with a test lung follows after these software checks pass.

The update has passed 12 host scenarios with simulated readings. The SAMD21 build and the physical checks below are pending.

## Build and upload

1. Open the repository folder containing `platformio.ini` in VS Code.
2. Run PlatformIO **Build**. If it fails, save the first complete error and stop before uploading.
3. With the SensorHub off, connect the pressure module to Sensor A2 using the verified cable.
4. Connect USB, stop any running Serial Monitor and upload the firmware.
5. Open Serial Monitor at 115200 baud. Keep the syringe and pressure input at rest during calibration.
6. If startup was missed, reset the board and reconnect Serial Monitor if required.

## Checks

| Check | Action | Required observation |
|---|---|---|
| Startup | Leave the pressure input at rest for calibration, approximately 4.5 seconds | CSV header, calibration rows, then `# READY`; subsequent rows have `sample_ok=1` and `baseline_ok=1` |
| Rest | Leave it at rest for 10 seconds | Rows continue; raw values stay near the logged baseline; no candidate events |
| Event counting | Apply three gentle positive pressure pulses, fully releasing pressure between them | One completed candidate per pulse, with baseline recovery between events; ending count is 3 after a fresh startup |
| Manual zero | With pressure at rest, type `z` in Serial Monitor | Calibration runs again and ends with `# READY`; completed count is preserved |
| Movement during calibration | Type `z` and introduce a gentle pressure change while samples are collected | If the sample range exceeds 80 counts, calibration fails and counting stays disabled |
| Retry after movement | Leave the input at rest and type `z` again | A successful calibration restores counting; no unfinished event from before calibration is counted |
| Missing module at startup | Power off, disconnect the pressure module, then power on | Calibration fails; raw fields are empty on failed reads, `sample_ok=0`, `baseline_ok=0`, and the candidate count stays 0 |
| Restore the setup | Power off, reconnect the module to A2, then power on at rest | Normal startup calibration succeeds again |

Record the actual result for each check. The 80-count movement limit is a provisional software check for this bench setup, not a physiological criterion. A stable applied pressure can pass it, so always zero with the pressure at rest. Do not disconnect the module while it is powered.

During normal acquisition, any returned read failure invalidates the baseline and aborts the current event. Healthy readings afterward remain `CAL_REQUIRED` until `z` completes successfully. This live fault path is covered by the host tests; the power-off connection checks above verify missing-module startup without requiring live unplugging.

## Read and save the output

CSV columns are:

| Column | Meaning |
|---|---|
| `t_ms` | Read-completion timestamp since MCU boot, in milliseconds |
| `raw` | Signed ADC count for a successful read; empty on failure |
| `baseline` | Accepted fixed resting baseline; empty when invalid |
| `delta` | Raw minus baseline; empty unless both are available |
| `state` | `CALIBRATING`, `CAL_REQUIRED`, `IDLE`, `POSITIVE_EVENT` or `NEGATIVE_EVENT` |
| `candidate_count` | Completed positive events since boot |
| `sample_ok` | 1 when the ADC read succeeded, otherwise 0 |
| `baseline_ok` | 1 when calibration was accepted by the software, otherwise 0 |

Messages beginning with `#` are comments containing calibration, fault or event details. Empty numeric fields mean unavailable data. For example, a valid raw reading can have `sample_ok=1` and `baseline_ok=0` after a calibration failure.

Copy a complete run, including its CSV header, into a file such as `experiments/pressure/logger_bench_01.csv`. Keep the `#` comments; when importing the file later, configure the reader to ignore those comment lines. This `.csv` location is not excluded by the current `.gitignore`, unlike `*.log`, `logs/`, `captures/` and `data/raw/`.

For each saved run, record the firmware commit, board revisions, pressure connection, what input was applied and whether the checks passed. A board reset restarts timestamps and counts; save a separate file for each boot session.

## Completion

This step is complete when the board builds and uploads, the CSV is readable, normal pulses produce one completed candidate each, and the calibration-failure and retry checks behave as described. Use a controlled airway/test-lung setup next to investigate how these signals relate to actual lung filling. These syringe checks do not validate breaths, delivered volume or ventilation effectiveness.
