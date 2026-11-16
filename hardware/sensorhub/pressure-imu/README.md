# K.E.V.I.N. — Pressure + two BHI360 IMUs on one SAMD21

**Status (2026-11-16):** v0.2 ran on the SAMD21: both BHI360 IMUs were repeatedly identified (`identified=1`), but pressure ADC writes returned I²C address NACK (`wire_status=2`). User confirmed **no pressure sensor was connected** and that individual female-to-female jumper wires on the IMUs sometimes disconnect. Hence the ADC failure is expected, and previous Bus A failure is not evidence of a faulty sensor or controller. **v0.3 now treats the pressure module as optional at boot; it is committed but not yet built or tested on hardware.** IMU orientation remains unavailable because the BHI360 firmware-boot problem is separate. Infant-manikin research only; not clinical use.

This is a **separate PlatformIO project** at `hardware/sensorhub/pressure-imu`. It does not overwrite the pressure test code or the experimental BHI360 firmware-boot code.

## Hardware layout

| Module | Physical connector | SAMD21 I²C bus | I²C address | Role |
| --- | --- | --- | --- | --- |
| SimModule Pressure v2.0.0 / MCP3426 ADC (MPXV5010GP) | Sensor A2 | SERCOM1, PA16/PA17, Arduino pins 11/13 | `0x68` | Read raw respiratory pressure samples |
| CHEST BHI360 IMU | Sensor A1 | Same SERCOM1 bus as pressure | `0x29` | Read-only identity/health status |
| HEAD BHI360 IMU | Sensor B1 | SERCOM2, PA12/PA13, Arduino pins 28/39 | `0x29` | Read-only identity/health status |

**This is intentional:** pressure `0x68` and CHEST `0x29` can coexist on Bus A. HEAD also uses `0x29`, but is on a **separate Bus B**. Both SERCOM interrupt handlers are present in the new program.

The earlier separate tests verified the pressure module on A2 and the two BHI360 identities on A1/B1. Running all three simultaneously on the physical wiring, including the shared bus electrical load, **still needs to be verified**.

Connect only the existing verified keyed cables, with all power **off**. The current board's connector pin order, voltage supply, and I²C pull-up arrangement must be checked before constructing new cables. Avoid adding external pull-up resistors or higher-voltage supplies without validating the board.

## What is implemented now

**Pressure — source adapted from `feature/pressure-demo-dashboard/src/main.cpp`:**
- MCP3426 CH1 `0x88` one-shot, 16-bit gain ×1 acquisition using the existing 100 ms conversion wait
- Manual `z` zero calibration at rest: 30 good samples, up to 45 attempts, max 80 ADC-count spread
- Positive and negative pressure excursion detection with provisional +200/-200 raw-count start thresholds and ±80-count return thresholds
- Candidate positive-event counting and duration/interval logs; preserves a previously accepted baseline if an attempted recalibration fails
- Raw-pressure CSV compatible in shape with the earlier pressure-dashboard project

**IMUs — safe integration stage only:**
- Periodically identify both BHI360s through read-only FUSER2 ID `0x89` and chip ID `0x7A` checks
- Read revision, boot-status, and error registers when the IDs match
- Report independent sensor-identification status on the same serial stream as pressure
- **NO** Bosch firmware upload, soft reset, quaternion, head-angle, calibrated motion, or sensor-fusion commands

The earlier crash report from `hardware/imu/dual-motion/diagnostics/2026-11-16-chest-crash-v0.8.md` shows firmware startup problems. The integrated program deliberately does not repeat those operations.

## First combined test and updated interpretation

User serial output, 2026-11-16: pressure ADC returned no valid samples and baseline calibration failed; CHEST BHI360 could not be identified; HEAD BHI360 on separate Bus B identified successfully. **Later information resolves most of this:** no pressure sensor was physically connected, explaining address NACK at `0x68`; CHEST and HEAD both became consistently identifiable in the next log. The shared bus is not proven faulty.

v0.2 adds a safe **`s`** serial command to test only the three known I2C addresses (no BHI360 firmware upload):

```text
# BUS_CHECK_BEGIN (address ACK only; no firmware writes)
# BUS_CHECK bus=A device=PRESSURE_ADC address=0x68 wire_status=0 ack=1
# BUS_CHECK bus=A device=CHEST_IMU address=0x29 wire_status=0 ack=1
# BUS_CHECK bus=B device=HEAD_IMU address=0x29 wire_status=0 ack=1
# BUS_CHECK_END
```

These rows illustrate **success**, not observed results. Actual status `0` means ACK; `2` usually means I2C address NACK; `3` data NACK; `4` other Wire error. v0.2 also emits `# ADC_DIAG reason=... wire_status=... rx_count=... returned_config=...` to distinguish I2C configuration NACK, short read, ADC conversion not ready, or unexpected ADC config. Repeated ADC fault messages are rate-limited.

**Next test (updated):** `git pull --ff-only`, PlatformIO Build, then Upload only if Build succeeds. Open Serial Monitor and confirm `PRESSURE_MODE ADC_NOT_DETECTED`, both IMU status lines and the slower `PRESSURE_ABSENT` CSV rows. No pressure calibration is possible until the module is connected at power-up. If Bus A IMU identification is intermittent, investigate the jumper-wire connections (power OFF first). If Bus A is still missing both devices, power off every supply first; inspect verified connectors/power and the specific board's A bus. If electrically safe and approved by the physical board documentation, test pressure alone on A2 with chest disconnected (power OFF before any connection change), then chest alone. Check power and SDA/SCL pull-ups; do not hot-plug, change supplies, or add arbitrary pull-ups.

## Optional pressure module (v0.3)

Because the pressure module is **not currently connected**, v0.3 tests its I2C address `0x68` only at startup, then enters `IMU_ONLY` if absent. It does **not** repeatedly write nonexistent ADC configuration registers or flood the terminal with ADC faults. The IMU status probes on A1 and B1 continue.

Expected when no MCP3426 is attached (illustrative, not hardware-verified):

```text
# BUS_CHECK bus=A device=PRESSURE_ADC address=0x68 wire_status=2 ack=0
# BUS_CHECK bus=A device=CHEST_IMU address=0x29 wire_status=0 ack=1
# BUS_CHECK bus=B device=HEAD_IMU address=0x29 wire_status=0 ack=1
# PRESSURE_MODE ADC_NOT_DETECTED (IMU_ONLY; pressure samples suppressed)
# IMU,CHEST,identified=1,revision=0x2,boot=0x18,error=0x0,motion=NOT_INITIALIZED
# IMU,HEAD,identified=1,revision=0x2,boot=0x18,error=0x0,motion=NOT_INITIALIZED
1000,,,,PRESSURE_ABSENT,0,0,0
# JOIN,1000,,,PRESSURE_ABSENT,0,0,0,1,1,
```

The empty pressure and neck-angle fields are deliberate: **no fabricated measurements**. Manual `z` reports a calibration skip when the pressure ADC was not detected at boot. To attach a pressure module later, power **everything off**, connect the verified pressure module and restart the SensorHub. Its presence is latched at boot; the `s` command may display live ACK changes but does not enable hot-plugging.

Individual female-to-female jumper wires on the IMUs are reported as physically sensitive and can come loose. Replace or secure the wiring with an electrically compatible **keyed/locking harness or correctly crimped multi-pin connectors** after checking the actual SensorHub and IMU board pinouts and supply voltage. Disconnect power before doing so. If an IMU disappears intermittently, treat its status as unavailable; `identified=1` only confirms register communication at the instant of the probe.

The existing pressure ADC read/zero/calibration and candidate-event logic is kept for when the module becomes available. **Actual pressure data and head/neck angles are not yet available in this combined configuration.**

## Output protocol

USB serial **115200 baud**. Ordinary CSV pressure rows remain unchanged:

```text
t_ms,raw,baseline,delta,state,candidate_count,sample_ok,baseline_ok
```

Additional read-only IMU status lines start with `# IMU,`:

```text
# IMU,CHEST,identified=1,revision=0x2,boot=0x18,error=0x0,motion=NOT_INITIALIZED
# IMU,HEAD,identified=1,revision=0x2,boot=0x18,error=0x0,motion=NOT_INITIALIZED
```

Additional joined records start with `# JOIN,`, so existing pressure-only CSV readers that skip comments are not disrupted.

```text
# JOIN_FIELDS,t_ms,raw,delta,state,candidate_count,sample_ok,baseline_ok,chest_identified,head_identified,neck_angle_deg
# JOIN,5100,2542,2,IDLE,0,1,1,1,1,
```

**These are illustrative rows, not a new hardware test.** All values are raw ADC counts. An empty `neck_angle_deg` is intentional; a number cannot be computed until both IMUs provide validated orientation data. `identified=1` proves correct device registers were read, **not** working motion output. `motion=NOT_INITIALIZED` is therefore expected.

Pressure rows may be sent during `CALIBRATING` and `CAL_REQUIRED` states; don't treat these as validated events. `#` messages should be ignored by a numeric-only pressure CSV parser. The integrated `# JOIN` rows can be parsed by a combined Raspberry Pi/dashboard consumer later.

## Commands

- `z` — recalibrate pressure at rest; counting remains inactive until an accepted baseline is available
- `p` — re-read both BHI360 device IDs and status registers now (read-only)
- `s` — read-only I2C ACK test for known addresses (A 0x68, A 0x29, B 0x29)
- `h` — show help

The firmware also probes IMUs automatically approximately every 2 seconds between pressure conversions. **There are no `c`, `b`, or `u` BHI360 upload commands in this new program.**

## Windows / PlatformIO first hardware test

1. Stop any existing serial monitor with **Ctrl+C**.
2. In the current cloned `K.E.V.I.N` repository, fetch the new branch and switch to it (the folder for this project will then appear):

   ```powershell
   git fetch origin
   git switch --track origin/feature/pressure-imu-integration
   cd ..\..\sensorhub\pressure-imu
   ```

   The `cd` line assumes the starting directory is `hardware\imu\dual-motion`. Alternatively, open `hardware\sensorhub\pressure-imu` from VS Code. Check that this folder contains its own `platformio.ini`.

3. Build first, without uploading:

   ```powershell
   & "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run
   ```

   If Build fails, do not upload; inspect the compiler error. This project does **not** require running `setup-bosch.ps1`.

4. After a successful build and memory check, power off, connect the three modules on their verified connectors and only then power up. Upload the integrated firmware:

   ```powershell
   & "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run -t upload
   ```

5. Open Serial Monitor with the SensorHub's actual COM port (it may not remain COM3):

   ```powershell
   & "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" device list
   & "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" device monitor -p COM3 -b 115200 -f send_on_enter
   ```

6. Observe `# IMU,CHEST,...` and `# IMU,HEAD,...`. First run `s` and check Bus A ACK; only if pressure and IMU communication is working, verify `sample_ok=1`. With no pressure applied, type **`z`** and press Enter; keep pressure at rest until `# READY`.
7. Using a gentle, controlled bench syringe setup, apply and release a pressure excursion. Confirm raw counts change, the baseline stays fixed, and an appropriate candidate event may be counted. Do not infer airflow, lung volume or patient ventilation effectiveness.
8. Type **`p`** while the system is running. Confirm both IMU identity/status lines still print, without disturbing the pressure reading. Share the first serial output and any faults.

## Acceptance criteria for stage 1

- Both IMUs respond as BHI360 devices in the **same run** as pressure sampling.
- MCP3426 returns valid raw readings and manual baseline calibration reaches `# READY`.
- Pressure excursions appear and event counting behaves consistently with the existing pressure test.
- `# JOIN` records carry correct pressure values and the two IMU identification flags.
- Firmware startup, periodic probes, and serial commands never request a BHI360 fusion upload.
- `neck_angle_deg` stays **empty** until measured chest/head quaternions are available.

## Next engineering milestones

1. Validate three-device simultaneous operation, electrical supply and I²C integrity (the pressure module and chest IMU now share Bus A).
2. Debug BHI360 command-channel upload exception using the archived crash data and Bosch guidance, separately from the pressure firmware.
3. Once **each IMU's quaternion stream is demonstrated on hardware**, add those streams and timestamps to the joined records. Calibrate head vs chest reference orientations and compute relative rotation, then verify it against known test angles.
4. Feed the combined stream to the Raspberry Pi / training-monitor simulator. Add airflow sensing separately if actual flow or delivered air volume is required.

**Important limitations:** The pressure sensor alone cannot measure flow, delivered air volume, or validate effective breaths; the IMUs cannot currently measure head/neck angle in this integration stage. Never present either as clinical measurements.
