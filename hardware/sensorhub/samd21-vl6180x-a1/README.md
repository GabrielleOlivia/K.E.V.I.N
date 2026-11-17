# SAMD21 Sensor A1 — live VL6180X ToF ranging

## Goal

Continue the successful **2026-11-17** SAMD21 VL6180X A1 identity test (`0x29 ACK=1`, `model ID 0xB4`, identified=1) by obtaining actual raw distance samples, with a moveable paper target.

This new branch does NOT overwrite the earlier read-only `feature/samd21-vl6180x-tof-a1-diagnostic` source. It reuses the STM32 test's working `vl6180x.h` driver (including the VL6180X mandatory initialization registers) and the SAMD21's already-tested PA16 SDA and PA17 SCL routing.

## Hardware and caution

1. Disconnect SAMD21 USB while changing cables.
2. Connect **only the VL6180X ToF** with the confirmed-compatible keyed four-wire cable to **Sensor A1** (sensor hub A / SERCOM1).
3. Disconnect pressure A2 and both BHI360 IMUs; the A1 chest IMU and VL6180X share I²C `0x29` and cannot coexist on bus A without isolation.
4. Only after verifying the sensor has 3.3V, GND, SDA and SCL pin-compatible with A1, reconnect USB.
5. This is a manikin bench diagnostic, not calibrated CPR compression depth nor human medical monitoring.

The firmware uses 100 kHz I²C, verifies model ID `0xB4`, runs the standard VL6180X initialization writes, and streams at approximately **4 samples per second**. It does **not** write firmware to IMUs.

## PowerShell build and upload

```powershell
cd "$env:USERPROFILE\Documents\K.E.V.I.N"
git fetch origin
git switch --track origin/feature/samd21-vl6180x-a1-live-ranging
cd .\hardware\sensorhub\samd21-vl6180x-a1
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run -t upload --upload-port COM3
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" device monitor -p COM3 -b 115200 -f send_on_enter
```

**Note:** Build+upload is not yet verified on physical SAMD21 for this branch. COM3 was the user's known SAMD21 port on 2026-11-17; `platformio device list` if changed. Close Serial Monitor before upload. Upload replaces currently installed read-only identity firmware and can be rolled back by rebuilding/re-uploading the earlier branch.

## Expected example output (not yet observed)

```text
# KEVIN SAMD21 VL6180X SENSOR A1 LIVE RANGING v0.2
# TOF_MODEL_ID value=0xB4 expected=0xB4 identified=1
# TOF_READY: streaming raw distances in mm at ~4 Hz
# tof,t_ms=4821,raw_mm=62,err=0,valid=1
# tof,t_ms=5072,raw_mm=83,err=0,valid=1
# tof,t_ms=5325,raw_mm=255,err=7,valid=0
```

Values above are fabricated **examples for formatting only**, not bench evidence. Valid raw distance samples require BOTH `err=0` and `valid=1`. `raw_mm=255` with nonzero error is invalid; it is NOT a measured 255 mm. The VL6180X has a practical short-distance range; start with plain white paper roughly **30–100 mm** from sensor and move smoothly closer or farther. Avoid touching the lens or shining a powerful IR source. Count only valid samples.

The firmware attempts identification again every 2 seconds after a failed start/read; *do not hotplug sensors* to force retries. Power OFF before cable changes.

Commands in Serial Monitor:
- `s`: rerun ToF identification and initialization
- `p`: pause/resume streaming
- `h`: help

If `# TOF_ABSENT`, check power and cable. If `# TOF_WRONG_DEVICE`, check for address conflicts. If `# TOF_READ_FAILED`, review bus/power and repeat only after checking. Initialization writes are standard VL6180X config; sensor is not left read-only.

## Prior results and separation

Previously verified on SAMD21: VL6180X A1 ACK and correct `0xB4` identity. Previously verified on STM32 Port A upper: VL6180X distances around 20–130 mm with `err=0`. The **current SAMD21 live range mode is new and not yet physically verified** as of this commit.

The separate STM32 pressure-module I²C issue is not affected by this test.

## Confirmed live hardware validation — 2026-11-17

The user flashed and ran this branch on the SAMD21 SensorHub with the VL6180X on Sensor A1. The COM3, 115200-baud serial monitor reported:

```text
# TOF_MODEL_ID value=0xB4 expected=0xB4 identified=1
# TOF_READY: streaming raw distances in mm at ~4 Hz
# tof,t_ms=6515,raw_mm=159,err=0,valid=1
# tof,t_ms=6764,raw_mm=47,err=0,valid=1
# tof,t_ms=17067,raw_mm=64,err=0,valid=1
# tof,t_ms=18078,raw_mm=12,err=0,valid=1
# tof,t_ms=18837,raw_mm=9,err=0,valid=1
# tof,t_ms=25449,raw_mm=255,err=7,valid=0
```

**Hardware test PASS** for sensor identification, VL6180X initialization, continuous raw ranging, and serial streaming. Valid raw samples in the supplied log range approximately **9–192 mm**; intervals with `err=6`, `err=7`, or `err=13` report `valid=0` and **must not be treated as real distance**. Values were observed while moving a target, so this test **does not yet quantify accuracy, precision, repeatability, or behavior against a stationary reference target**.

Sensor A1 0x29 shares an address with the chest BHI360; do not reconnect that IMU to the same I2C bus without address isolation or a different bus. STM32 MCP3426 pressure-ADC communication remains an independent unresolved issue.
