# K.E.V.I.N. — Dual BHI360 motion-stream prototype (v0.9: corrected postmortem decoding)

**Status:** Earlier v0.2 compiled and flashed successfully on SAMD21, but neither BHI360 booted motion firmware. v0.3 preflight **built, flashed, and passed on both IMUs**. v0.4 was built and flashed; the CHEST attempt failed with Wire status 3 (data NACK) on register 0x00, 28 bytes, Bosch error `0x44` (unhandled interrupt / exception; postmortem potentially available). v0.5 was compiled and uploaded; the chest IMU NACKed write #4 after accepting just 84 command-channel bytes in 13 ms, and reported fatal error `0x44`, debug state `0x0B`. v0.6 compiled and ran on the SAMD21; manually requesting a CHEST postmortem after restarting/uploading returned `error=0x00` and skipped the request, so crash evidence was not available at that time. v0.7 compiled and ran on hardware; after the chest upload failed with `0x44`, Bosch reported a **4300-byte** postmortem response but returned `-6` because our diagnostic buffer held only 4096 bytes. v0.8 **successfully built, flashed and retrieved a 4300-byte CHEST postmortem**, confirming unhandled interrupt `0x44` after three successful 28-byte host-channel writes. Its initial decoded-field offsets were wrong; v0.9 corrects the decoder according to Bosch datasheet Table 34. **v0.9 has not yet been compiled or hardware-tested.** On 2026-11-16: chest firmware upload had error value `0x11` (bad header CRC); head firmware verification succeeded (`0x38`) but boot produced `0x1B` (fatal firmware error). No motion/quaternion data obtained. Preserve the proven `hardware/imu/diagnostics` project. For infant *manikin simulation only*, not clinical or patient monitoring.

## Evidence saved in repository

- [2026-11-16 CHEST crash dump, exact 224-byte prefix, Bosch Table 34 decoded fields](diagnostics/2026-11-16-chest-crash-v0.8.md)
- The decoder in v0.8 wrongly subtracted 4 bytes from Table 34 offsets. The corrected offsets give `crash_valid=1`, `flags=0x06`, `stack_size=4096`, `reset_reason=0x04`, `error_report=0x44`. v0.9 source fixes this; these conclusions come directly from the already captured v0.8 hex dump, so **no immediate new upload is required**.

## Hardware confirmed by diagnostic output (2026-11-16)

| SensorHub | Role | I2C bus | Address | Device ID |
| --- | --- | --- | --- | --- |
| A1 | Chest IMU | Bus A / SERCOM1 PA16/PA17 | 0x29 | FUSER2_ID 0x89 (ACK) |
| B1 | Head IMU | Bus B / SERCOM2 PA12/PA13 | 0x29 | FUSER2_ID 0x89 (ACK) |

Both devices were read twice successfully. This does not prove firmware/sensor fusion is running. Connect/disconnect sensors only with USB power removed. Do not alter wiring that gave the successful identification output.

## Current controlled diagnostic (v0.9)

On power-up the program performs **read-only preflight** for both modules, displaying FUSER2 ID, chip ID, revision, ROM version, boot status, error code and error auxiliary register. It **does not automatically reset or upload firmware**. This prevents inadvertently repeating failed firmware operations on each USB reconnection or MCU reset.

**Stop firmware-upload retries for now.** The v0.8 capture provides a valid crash report already: flags `0x06`, stack size 4096, reset reason `0x04`, error report `0x44` (unhandled interrupt), ECR `0x00020100`. We do not need another `c`/ `b` test simply to reproduce that information. Preserve the existing working preflight and do not change wiring under power. The former `u` command that affected both sensors remains disabled.

Serial commands:
- `p`: repeat read-only preflight
- `h`: show help
- `d`: **once per MCU session**, request a CHEST postmortem crash dump manually (only when an error is present). This is a command-channel request, not a firmware upload. In v0.6, the error had cleared by the time this was requested.
- `c`: **one** firmware-upload/boot attempt on the CHEST IMU alone. If the upload or boot fails, v0.8 immediately attempts to retrieve postmortem data **before any reset**, even if the error register already reads 0. HEAD is left untouched.
- `b`: **one** firmware-upload/boot attempt on the HEAD IMU alone, with the same automatic failure-capture logic. **Do not use for the next chest test.** CHEST is left untouched.
- `u`: disabled.

For each IMU, attempts are limited to once per SAMD21 session. **Avoid automatic repeats**; inspect all diagnostic output, then power-cycle before any later attempt. Motion measurement remains unverified.

## What the eventual motion prototype attempts

1. Verify each BHI360 FUSER2 identifier before configuration writes.
2. Initialize two independent Bosch API instances on the separate I2C buses.
3. Load the official Bosch **bsxsam_lite** 6-axis firmware image to a **single selected** IMU on an explicit serial command. Include the image only once in SAMD21 flash.
4. Enable Game Rotation Vector at 25 Hz on both.
5. Read each sensor FIFO and stream measured quaternions over USB serial (115200 baud).

Game Rotation Vector does not require an external magnetometer but yaw may drift. Both IMUs require frame alignment and calibration before interpreting their relative orientation as a head/neck angle.

## VS Code / Windows workflow (from K.E.V.I.N. repository root)

1. Stop any running serial monitor with Ctrl+C.
2. Fetch and switch to `feature/dual-bhi360-motion`, then open the directory `hardware/imu/dual-motion` as its own VS Code PlatformIO project. Do not open `hardware/imu/diagnostics` for this build.
3. In that project's terminal, retrieve the pinned official Bosch SensorAPI + firmware (requires Git and internet):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-bosch.ps1
```

4. Run **PlatformIO: Build** first. Verify flash/RAM usage; the SAMD21 has limited flash. If Build fails, **do not upload**—share the last error lines.
5. Only if Build succeeds, run **PlatformIO: Upload** (this replaces the currently flashed SAMD21 program; the earlier diagnostic remains preserved in Git). The *v0.8 application is read-only until explicitly commanded*.
6. Open serial monitor:

```powershell
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" device monitor -p COM3 -b 115200
```

If the port number changes, substitute the detected port.

Expected *illustrative only* v0.9 read-only preflight beginning:

```text
# KEVIN Dual BHI360 GameRV v0.9 CRASH-DECODE-FIX
# Sensor A1=CHEST, Sensor B1=HEAD, both at I2C 0x29
# CHEST PREFLIGHT_BEGIN (reads only)
# CHEST fuser2_id=0x89
...
# HEAD PREFLIGHT_BEGIN (reads only)
...
# No automatic firmware upload. After manual c/b failure, crash capture runs before reset.
```

There should be **no** `loading ... firmware bytes` or `Q,...` lines at startup. In v0.7, a **single manual** `c` test (after checking the preflight and completing a proper power cycle if needed) performs the upload as before, but now automatically requests a Bosch crash dump immediately on failure. Capture `MANUAL_LITE_CHEST_BEGIN` through `POSTMORTEM_END` or `POSTMORTEM_SKIPPED`. v0.5's previously measured failure was command-channel write #4 (28 bytes) after 84 bytes accepted and 13 ms elapsed, even with a 1 ms pause. This remains a bootloader/transfer investigation, not a validated orientation system. No clinical use. Captured values may reflect residual sensor error state from the previous run. Power off before rewiring; do not infer that working I2C proves the connector voltage is safe.

## Limits

- Copies successful SAMD21 wiring from identification probe.
- Uses Bosch SensorAPI v2.3.1 with the official `Bosch_Shuttle3_BHI360_bsxsam_lite.fw.h` firmware image and I2C transactions of at most 28 data bytes. Testing a smaller image isolates one possible factor but does not establish hardware compatibility.
- No BMM350, pressure driver, angle calculation, or Raspberry Pi host code yet.
- Sensor readings aren't hardware-synchronized; serial frames include host `millis()` and `age_ms`.
- Firmware never erases nonvolatile storage in the BHI360; uploads to RAM, but replaces the program flashed on the SAMD21.
- No build or on-hardware result has been verified for this prototype.

## References

- https://github.com/boschsensortec/BHI360_SensorAPI
- https://github.com/boschsensortec/BHI360_SensorAPI/blob/v2.3.1/examples/quaternion/quaternion.c
- https://github.com/GabrielleOlivia/K.E.V.I.N/tree/feature/bhi360-imu-diagnostics/hardware/imu/diagnostics
