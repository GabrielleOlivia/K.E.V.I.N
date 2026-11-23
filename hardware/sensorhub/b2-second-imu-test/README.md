# K.E.V.I.N. — second IMU (physical Sensor B2) bench test

**Status: SOURCE PREPARED. Not built, flashed or tested on the actual SAMD21 yet.** This is a *separate project* from the working three-sensor scanner and the live-monitor simulator. Only the second IMU should be connected while testing. Do not use the original scanner's `g` command with an IMU on Bus B: that command assumes a VL6180X ToF at `0x29`.

## Evidence from 23 November 2026

User's COM3 scans repeatedly returned exactly `0x14` and `0x28` on `bus=B2` (four additional successful consecutive scans, on top of two earlier), with no extra addresses. These are the candidate BMM350 (`0x14`) and BHI360 (`0x28`) alternate I²C addresses. This only establishes ACK responses, **not** chip identity or live motion readings.

### What is new

- **Stage 1 (`b2_imu_id_only`, default):** Read-only scan plus independent **BHI360 chip ID register `0x2B` expected `0x7A`** and **BMM350 chip ID register `0x00` expected `0x33`**. The BMM350 read **throws away two mandatory I²C dummy bytes**. Does not reset, configure or initialize any IMU. Does not require Bosch libraries.
- **Stage 2 (`b2_imu_accel`):** Optional experimental Bosch BHI360 SensorAPI with the official `bsxsam_lite` firmware. Only after *both* chip IDs match, the operator may explicitly send `m` to load BHI360 firmware into the sensor's RAM, enable its calibrated accelerometer virtual sensor and request real X/Y/Z raw sample frames.
- Uses **only SERCOM2**, PA12/PA13, Feather M0 indices 28/39. It **does not** start or scan Sensor A. Physical B2 shares the electrical bus with B1, so B1 must be empty.

**Caution:** Although both I²C devices appeared six times, their wiring and supply must be verified against the *actual* SensorHub board. The archived B2 reference has a fifth **VSYS/5 V** net contact. Do not blindly shift a four-wire connector by one position. Disconnect USB and **all other supplies** before inspecting or changing cables. Stop if anything heats, smells abnormal, or if unexpected addresses appear. Bench training equipment only.

## Start from GitHub (Windows PowerShell)

To preserve your current working checkout, create a **separate Git worktree**. If `git worktree add` says that the branch/path is already in use, open the existing folder rather than duplicating it.

```powershell
cd "$env:USERPROFILE\Documents\KEVIN-a2-b2-review"
git fetch origin
git worktree add -b b2-imu-test "$env:USERPROFILE\Documents\KEVIN-B2-IMU" origin/feature/b2-second-imu-xyz-test-2026-11-23
cd "$env:USERPROFILE\Documents\KEVIN-B2-IMU\hardware\sensorhub\b2-second-imu-test"
$pio = "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe"
```

### Step 1 — Compile the ID-only firmware **first**, not the motion firmware

```powershell
& $pio run -e b2_imu_id_only
```

**Stop here and inspect the compile result** before uploading. We have not executed a real PlatformIO compile in this environment. If it succeeds, after verifying the B2 wiring and confirming COM3 refers to your SensorHub, and after closing any serial monitor/application, the opt-in upload command is:

```powershell
& $pio run -e b2_imu_id_only -t upload --upload-port COM3
& $pio device monitor -p COM3 -b 115200 -f send_on_enter -f log2file
```

The *new* firmware starts Bus B automatically, so **do not enter `b`**. Enter these **one at a time** in the monitor:

```text
i
s
```

Example **expected** (not a measured result):

```text
# KEVIN B2 IMU TEST v1 BHI360@0x28 BMM350@0x14
# BUILD=READ_ONLY_ID; i=scan; s=chip IDs; h=help; no sensor boot writes
# B2_BUS_READY send i then s
# SCAN_START bus=B2
# SCAN_FOUND bus=B2 address=0x14
# SCAN_FOUND bus=B2 address=0x28
# SCAN_END bus=B2 count=2
# BHI360_B2 chip_id=0x7A expected=0x7A
# BMM350_B2 chip_id=0x33 expected=0x33
# B2_IMU_IDENTIFIED BOTH_CHIPS
```

If either ID differs or reads fail, **do not proceed to Stage 2**; send the actual log instead. A read-only identity check is much less intrusive than initializing Bosch firmware.

### Step 2 — Optional accelerometer X/Y/Z streaming

Only if Stage 1 succeeds and you choose to test motion, close the monitor with `Ctrl+C` and, **without touching the powered wiring**, run:

```powershell
py -3 scripts/vendor_bhi360.py
& $pio run -e b2_imu_accel
```

This downloads **Bosch's official open-source SensorAPI**, the `bsxsam_lite` firmware C header and its BSD-3-Clause license *into the ignored local `lib/BHI360Vendor` folder*. It records the upstream Git commit. GitHub holds the project source; the vendor script fetches the sizeable manufacturer dependency. The script does not flash the SAMD21.

**Check the actual build result and flash/RAM utilization**. Do not upload if compilation or linking fails. If it succeeds and you understand that this is *untested experimental firmware*, upload:

```powershell
& $pio run -e b2_imu_accel -t upload --upload-port COM3
& $pio device monitor -p COM3 -b 115200 -f send_on_enter -f log2file
```

In the new monitor send `i`, `s`, then **`m`** to initialize the BHI360. Do not send `g` (it isn't a command in this test).

Expected *format*, not verified on hardware:

```text
# IMU_FIRMWARE_START B2 BHI360@0x28 experimental
# IMU_READY B2 accel_virtual_sensor=4 kernel=...
# accel,t_ms=1234,x_raw=...,y_raw=...,z_raw=...,valid=1,sensor=BHI360_B2
```

Hold the IMU still, then gently rotate it about two different axes. At rest the gravity component should move between axes as the orientation changes. We print raw signed samples **without claiming calibrated g-units, heading, head angle, or accurate degrees**. The BMM350 is only identity-checked in this stage; it is **not** streamed or used for sensor fusion.

If `# IMU_FAULT` occurs, stop and save the log. The `# IMU_READY` message alone does not prove XYZ measurements until **actual varying sensor samples** appear.

### Roll back to the original scanner

From the *existing original review* project folder, **only after backing up logs and confirming the correct COM port**, close all programs using COM3:

```powershell
cd "$env:USERPROFILE\Documents\KEVIN-a2-b2-review\hardware\sensorhub\samd21-pressure-a2-tof-b2"
$pio = "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe"
& $pio run -e adafruit_feather_m0_express -t upload --upload-port COM3
```

The original scanner source is **untouched on GitHub**. Reflashing replaces the test firmware on the SAMD21, not any git files. **Do not send `g` when the IMU is on Bus B**, even after rollback.

## Engineering notes

- Official manufacturer references: [Bosch BHI360 SensorAPI](https://github.com/boschsensortec/BHI360_SensorAPI), [Bosch BMM350 SensorAPI](https://github.com/boschsensortec/BMM350_SensorAPI), and their published datasheets.
- The accelerometer virtual sensor requires firmware startup and FIFO processing; an address-only scan never provides X/Y/Z data.
- The fallback `bsxsam_lite` image omits external BMM350 fusion; the magnetometer remains untouched beyond chip-ID reads.
- SDK compatibility, heap/flash/RAM limits, bus timing and I²C reliability have **not** been physically validated. The firmware does no I²C writes until the operator explicitly issues the accelerometer startup command `m` in Stage 2 (apart from the standard address/register-selection operations required for read-only inspection).
- When a failure is reported, do not silently interpret stale data as valid. No motor, speaker, CPR actuator or patient output is controlled by this code.
