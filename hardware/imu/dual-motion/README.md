# K.E.V.I.N. — Dual BHI360 motion-stream prototype (v0.5: paced-transfer diagnostics)

**Status:** Earlier v0.2 compiled and flashed successfully on SAMD21, but neither BHI360 booted motion firmware. v0.3 preflight **built, flashed, and passed on both IMUs**. v0.4 was built and flashed; the CHEST attempt failed with Wire status 3 (data NACK) on register 0x00, 28 bytes, Bosch error `0x44` (unhandled interrupt / exception; postmortem potentially available). v0.5 has **not yet been compiled or hardware-tested**. On 2026-11-16: chest firmware upload had error value `0x11` (bad header CRC); head firmware verification succeeded (`0x38`) but boot produced `0x1B` (fatal firmware error). No motion/quaternion data obtained. Preserve the proven `hardware/imu/diagnostics` project. For infant *manikin simulation only*, not clinical or patient monitoring.

## Hardware confirmed by diagnostic output (2026-11-16)

| SensorHub | Role | I2C bus | Address | Device ID |
| --- | --- | --- | --- | --- |
| A1 | Chest IMU | Bus A / SERCOM1 PA16/PA17 | 0x29 | FUSER2_ID 0x89 (ACK) |
| B1 | Head IMU | Bus B / SERCOM2 PA12/PA13 | 0x29 | FUSER2_ID 0x89 (ACK) |

Both devices were read twice successfully. This does not prove firmware/sensor fusion is running. Connect/disconnect sensors only with USB power removed. Do not alter wiring that gave the successful identification output.

## Current safe test (v0.3)

On power-up the program performs **read-only preflight** for both modules, displaying FUSER2 ID, chip ID, revision, ROM version, boot status, error code and error auxiliary register. It **does not automatically reset or upload firmware**. This prevents inadvertently repeating failed firmware operations on each USB reconnection or MCU reset.

**Stop after preflight and review the results. For the next controlled test, use `c` only after confirming v0.5 is running and a full power cycle has returned the error register to 0.** The former `u` command that affected both sensors is disabled.

Serial commands:
- `p`: repeat read-only preflight
- `h`: show help
- `c`: **one** firmware-upload/boot attempt on the CHEST IMU alone. HEAD is left untouched.
- `b`: **one** firmware-upload/boot attempt on the HEAD IMU alone. CHEST is left untouched.
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
5. Only if Build succeeds, run **PlatformIO: Upload** (this replaces the currently flashed SAMD21 program; the earlier diagnostic remains preserved in Git). The *v0.3 application is read-only until explicitly commanded*.
6. Open serial monitor:

```powershell
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" device monitor -p COM3 -b 115200
```

If the port number changes, substitute the detected port.

Expected *illustrative only* v0.5 read-only preflight beginning:

```text
# KEVIN Dual BHI360 GameRV v0.5 PACED-TRANSFER DIAGNOSTIC
# Sensor A1=CHEST, Sensor B1=HEAD, both at I2C 0x29
# CHEST PREFLIGHT_BEGIN (reads only)
# CHEST fuser2_id=0x89
...
# HEAD PREFLIGHT_BEGIN (reads only)
...
# At startup no firmware is uploaded. Review log before typing c or b.
```

There should be **no** `loading ... firmware bytes` or `Q,...` lines at startup. After typing `c`, inspect the full CHEST status lines and stop before testing the HEAD (`b`). v0.5 inserts a 1 ms pause after successful 28-byte command-channel writes and reports count of acknowledged writes, channel bytes, failed write number and elapsed time, along with debug state/value registers. These are diagnostic experiments; they **do not establish the cause or guarantee a fix**. Error 0x44 is not the same as error 0x76 (upload overflow). Captured values may reflect residual sensor error state from the previous run. Power off before rewiring; do not infer that working I2C proves the connector voltage is safe.

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
