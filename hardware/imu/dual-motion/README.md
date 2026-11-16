# K.E.V.I.N. — Dual BHI360 motion-stream prototype (experimental v0.1)

**Status:** Source prototype, **not compiled or tested on SAMD21 hardware yet**. Preserve the proven `hardware/imu/diagnostics` project. For infant *manikin simulation only*, not clinical or patient monitoring.

## Hardware confirmed by diagnostic output (2026-11-16)

| SensorHub | Role | I2C bus | Address | Device ID |
| --- | --- | --- | --- | --- |
| A1 | Chest IMU | Bus A / SERCOM1 PA16/PA17 | 0x29 | FUSER2_ID 0x89 (ACK) |
| B1 | Head IMU | Bus B / SERCOM2 PA12/PA13 | 0x29 | FUSER2_ID 0x89 (ACK) |

Both devices were read twice successfully. This does not prove firmware/sensor fusion is running. Connect/disconnect sensors only with USB power removed. Do not alter wiring that gave the successful identification output.

## What this project attempts

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
5. Only if Build succeeds, run **PlatformIO: Upload** (this will replace the running diagnostic firmware, which remains preserved in Git).
6. Open serial monitor:

```powershell
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" device monitor -p COM3 -b 115200
```

If the port number changes, substitute the detected port.

Expected *illustrative* boot lines:

```text
# CHEST BHI360 ID verified
# CHEST api_init result=0
# CHEST enable_game_rotation_vector result=0
# HEAD BHI360 ID verified
# HEAD api_init result=0
# HEAD enable_game_rotation_vector result=0
# CSV: Q,LOCATION,host_ms,qx,qy,qz,qw,accuracy_rad,age_ms
Q,CHEST,123456,0.01000,0.04000,0.00100,0.99900,0.05000,3
Q,HEAD,123456,0.01200,0.23000,0.00300,0.97300,0.05000,4
```

This output is **not measured data**. If initialization produces an error or no `Q` lines appear, capture the exact output; stop and investigate before repeating uploads.

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
