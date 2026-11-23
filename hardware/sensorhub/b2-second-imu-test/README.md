# K.E.V.I.N. — second IMU (physical Sensor B2) bench test

**Status: B2 identity test PASSED on hardware and the optional XYZ firmware COMPILED successfully on Windows; upload and physical XYZ readings are not yet verified.** This is a *separate project* from the working three-sensor scanner and the live-monitor simulator. Only the second IMU should be connected while testing. Do not use the original scanner's `g` command with an IMU on Bus B: that command assumes a VL6180X ToF at `0x29`.

## First physical BHI360 startup attempt — 23 November 2026 (FAILED at sensor-list I²C)

User-reported COM3 output (experimental build, second IMU alone on B2):

```text
# BHI360_B2 chip_id=0x7A expected=0x7A
# BMM350_B2 chip_id=0x33 expected=0x33
# B2_IMU_IDENTIFIED BOTH_CHIPS
# IMU_FIRMWARE_START B2 BHI360@0x28 experimental
# IMU_UPLOAD bytes=0 total=82648
...
# IMU_UPLOAD bytes=79872 total=82648
# IMU_FAULT stage=accelerometer_not_available code=-3
```

**Evidence and diagnosis:** Bosch's header defines `BHI360_E_IO=-3`, not "sensor absent." The stage in our old code combined the returned error from `bhi360_update_virtual_sensor_list` with the availability check. Bosch's `bhi360_system_param_get_virtual_sensor_present` asks for a **32-byte** buffer; our previous `readBosch` callback rejected any read **over 28 bytes**, which is sufficient to produce this exact I/O error. It is a plausible and directly supported firmware bug, not proof that hardware is defective. The last firmware-upload progress message does not independently confirm valid X/Y/Z output; kernel-version read appears to have succeeded since the code reached the sensor-list check.

**Fix applied (not yet hardware-retested):** The BHI360 I²C RX callback now permits up to **32 bytes** while keeping the conservative 28-byte write limit. Adafruit's SAMD21 Arduino `TwoWire` library has a 256-byte RX ring buffer. The code reports `# IMU_I2C_READ_REJECT`/`# IMU_I2C_READ_SHORT` if a transfer is rejected/short, `# IMU_FAULT stage=virtual_sensor_list_io code=...` if Bosch list retrieval fails, and `# IMU_SENSOR_LIST_READY accel_available=1` if present.

Rebuild/flash with only this B2 IMU connected and no other program using COM3:

```powershell
cd "$env:USERPROFILE\Documents\KEVIN-B2-IMU\hardware\sensorhub\b2-second-imu-test"
git fetch origin
git merge --ff-only origin/feature/b2-second-imu-xyz-test-2026-11-23
$pio = "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe"
& $pio run -e b2_imu_accel
# If SUCCESS and memory remains within limits, optional flash:
& $pio run -e b2_imu_accel -t upload --upload-port COM3
& $pio device monitor -p COM3 -b 115200 -f send_on_enter -f log2file
```

At the monitor, check `i`, `s`, then explicitly `m` once. If a new failure occurs, preserve the full log instead of repeatedly initializing. No real accelerometer samples are confirmed yet.

## Verified Windows build — 23 November 2026

**User-reported actual PlatformIO build output after the Bosch SDK port fix:**

```text
& $pio run -e b2_imu_accel -t clean
[SUCCESS] Took 0.60 seconds

& $pio run -e b2_imu_accel
RAM:   14.7% (used 4816 bytes from 32768 bytes)
Flash: 39.0% (used 102340 bytes from 262144 bytes)
Building .pio\\build\\b2_imu_accel\\firmware.bin
[SUCCESS] Took 3.82 seconds
```

- Target: Adafruit Feather M0 Express / SAMD21G18A, 48 MHz, 32 KiB RAM, 256 KiB flash; `atmelsam@9.0.0`, Arduino framework.
- Bosch vendor source commit printed by installer: `6b4696f84fd65185f85f10c391a7abd3d3602bf1`.
- The compile and link **passed** with the patched Bosch embedded-source subset. `firmware.bin` was generated. This confirms build viability and adequate statically reported memory, **not** sensor initialization or runtime FIFO data.
- **Next test remains UNVERIFIED:** optional flash to COM3, then `i`, `s`, and finally `m` with ONLY the physical B2 IMU connected. Check for `# IMU_READY...` and actual changing `# accel,...,valid=1` readings; report any `# IMU_FAULT`. Do not use `g`. Power off before rewiring.

## BHI360 accelerometer build fix — 23 November 2026

The first real Windows `pio run -e b2_imu_accel` **FAILED** at compile time (hardware not implicated):

- `bhi360_event_data_defs.h:146: non-trivial designated initializers not supported`: Bosch's upstream header contains three C99 lookup arrays which GCC 9's Arduino C++ compiler cannot parse as C++.
- `bhi360_parse.c:41: fatal error: verbose.h: No such file or directory`: the original vendoring installed host-side Bosch/COINES examples as though they were embedded driver code.

**Fix committed:** `scripts/vendor_bhi360.py` now (1) limits PlatformIO compilation to six required Bosch driver C source files, excluding the host example parser, and (2) hides only the three unused C99 lookup arrays when included by Arduino C++ while keeping them intact for Bosch C source. It creates `lib/BHI360Vendor/KEVIN_BHI360_PLATFORMIO_PORT_v1.txt`; on the next run it automatically replaces the previously installed unpatched vendor folder. There is **no edit to `src/main.cpp`**, to any tested chip-ID behavior, or to the original scanner. PlatformIO build success has **not** been confirmed after this fix.

From **this** Git worktree's `hardware/sensorhub/b2-second-imu-test` directory:

```powershell
git fetch origin
git merge --ff-only origin/feature/b2-second-imu-xyz-test-2026-11-23
$pio = "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe"
py -3 scripts/vendor_bhi360.py
& $pio run -e b2_imu_accel -t clean
& $pio run -e b2_imu_accel
```

Review compiler/linker success and **flash/RAM usage** before any upload. If new failures appear, save the full log. Do not edit Bosch headers manually or upload on a failed build.

## Confirmed physical chip-ID test — 23 November 2026

**Actual user-reported COM3 output from the read-only B2 test firmware:**

```text
# SCAN_START bus=B2
# SCAN_FOUND bus=B2 address=0x14
# SCAN_FOUND bus=B2 address=0x28
# SCAN_END bus=B2 count=2
# SCAN_START bus=B2
# SCAN_FOUND bus=B2 address=0x14
# SCAN_FOUND bus=B2 address=0x28
# SCAN_END bus=B2 count=2
# BHI360_B2 chip_id=0x7A expected=0x7A
# BMM350_B2 chip_id=0x33 expected=0x33
# B2_IMU_IDENTIFIED BOTH_CHIPS
```

**Interpretation:** Both chip-identity reads passed with exactly the expected chip IDs, beyond prior address-level ACKs. Two consecutive scans in this log also found only the expected addresses. This establishes short-term I²C/identity communication with the only connected IMU, **not** X/Y/Z data, sustained timing, mechanical mounting quality, or sensor fusion. The source corresponds to the read-only `b2_imu_id_only` stage; exact flashed binary hash not recorded.

**Next:** close serial monitor; install official Bosch SDK locally using `py -3 scripts/vendor_bhi360.py`; `& $pio run -e b2_imu_accel` (BUILD ONLY). Examine build output and memory consumption before optionally uploading or using command `m`. The experimental motion firmware remains unvalidated on hardware.

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
