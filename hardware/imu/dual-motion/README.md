# K.E.V.I.N. — Dual BHI360 motion-stream prototype (read-only preflight v0.3)

**Status:** Earlier v0.2 compiled and flashed successfully on SAMD21, but neither BHI360 booted motion firmware. v0.3 changes are **not yet built or tested**. On 2026-11-16: chest firmware upload had error value `0x11` (bad header CRC); head firmware verification succeeded (`0x38`) but boot produced `0x1B` (fatal firmware error). No motion/quaternion data obtained. Preserve the proven `hardware/imu/diagnostics` project. For infant *manikin simulation only*, not clinical or patient monitoring.

## Hardware confirmed by diagnostic output (2026-11-16)

| SensorHub | Role | I2C bus | Address | Device ID |
| --- | --- | --- | --- | --- |
| A1 | Chest IMU | Bus A / SERCOM1 PA16/PA17 | 0x29 | FUSER2_ID 0x89 (ACK) |
| B1 | Head IMU | Bus B / SERCOM2 PA12/PA13 | 0x29 | FUSER2_ID 0x89 (ACK) |

Both devices were read twice successfully. This does not prove firmware/sensor fusion is running. Connect/disconnect sensors only with USB power removed. Do not alter wiring that gave the successful identification output.

## Current safe test (v0.3)

On power-up the program performs **read-only preflight** for both modules, displaying FUSER2 ID, chip ID, revision, ROM version, boot status, error code and error auxiliary register. It **does not automatically reset or upload firmware**. This prevents inadvertently repeating failed firmware operations on each USB reconnection or MCU reset.

**Stop after the preflight output and inspect it first. Do not send `u` until the results have been reviewed.**

Serial commands:
- `p`: repeat read-only preflight
- `h`: show help
- `u`: explicitly attempt firmware upload and boot on both IMUs **once per MCU session**. This remains experimental and may produce errors. **Do not use for the next test until instructed.**

## What the eventual motion prototype attempts

1. Verify each BHI360 FUSER2 identifier before configuration writes.
2. Initialize two independent Bosch API instances on the separate I2C buses.
3. Load the same official Bosch bsxsam 6-axis fusion image to each IMU's RAM (once per sensor power cycle). Include the image only once in SAMD21 flash.
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

Expected *illustrative only* read-only preflight beginning:

```text
# KEVIN Dual BHI360 GameRV v0.3 PREFLIGHT
# Sensor A1=CHEST, Sensor B1=HEAD, both at I2C 0x29
# CHEST PREFLIGHT_BEGIN (reads only)
# CHEST fuser2_id=0x89
...
# HEAD PREFLIGHT_BEGIN (reads only)
...
# STOP after preflight and share the log. Do NOT send u until the log is reviewed.
```

There should be **no** `loading ... firmware bytes` or `Q,...` lines at startup. Captured values may reflect residual sensor error state from the previous run. Power off before rewiring; do not infer that working I2C proves the connector voltage is safe.

## Limits

- Copies successful SAMD21 wiring from identification probe.
- Uses Bosch SensorAPI v2.3.1 and I2C transactions of at most 28 data bytes.
- No BMM350, pressure driver, angle calculation, or Raspberry Pi host code yet.
- Sensor readings aren't hardware-synchronized; serial frames include host `millis()` and `age_ms`.
- Firmware never erases nonvolatile storage in the BHI360; uploads to RAM, but replaces the program flashed on the SAMD21.
- No build or on-hardware result has been verified for this prototype.

## References

- https://github.com/boschsensortec/BHI360_SensorAPI
- https://github.com/boschsensortec/BHI360_SensorAPI/blob/v2.3.1/examples/quaternion/quaternion.c
- https://github.com/GabrielleOlivia/K.E.V.I.N/tree/feature/bhi360-imu-diagnostics/hardware/imu/diagnostics
