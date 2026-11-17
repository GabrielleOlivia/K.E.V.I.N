# SAMD21 Sensor A bus (physically A2) — VL6180X read-only test

This is an isolated test of the *ToF sensor* on the older Feather M0 Express (SAMD21) carrier, not a pressure sensor test. It is deliberately separate from the integrated pressure/IMU firmware and does not alter that source.

## Test setup

- **Disconnect USB power before any wiring changes.**
- Remove pressure module (A2) and both IMUs (A1/B1).
- Plug *only* the VL6180X ToF using a confirmed-compatible keyed connector into **Sensor A2**.
- Confirm the actual port/cable pin order and power rails (GND, 3.3 V, SDA, SCL) before powering; same connector shape is not proof of pin compatibility.
- Sensor A2 is on I2C SERCOM1: SAMD21 **PA16 SDA**, **PA17 SCL**; VL6180X expected address **0x29**.
- The chest BHI360 IMU also uses **0x29**. It must not be connected to this bus at the same time.

## What the firmware does

At 100 kHz I2C: (1) address-ACK at `0x29`; (2) if responding, read the VL6180X model ID register at `0x0000`, expected `0xB4`. This performs no sensor reset/configuration write and does **not** measure distance. The previous pressure/IMU firmware's "CHEST_IMU address=0x29" label must **not** be used as proof of a ToF identification, because it assumes the wrong chip.

## Build and upload

On Windows PowerShell, after confirming sensor A2 wiring:

```powershell
cd "$env:USERPROFILE\Documents\K.E.V.I.N"
git fetch origin
git switch --track origin/feature/samd21-vl6180x-tof-a1-diagnostic
cd .\hardware\sensorhub\samd21-vl6180x-a1
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run -t upload --upload-port COM3
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" device monitor -p COM3 -b 115200 -f send_on_enter
```

COM3 is the previously observed SAMD21 COM port; re-run `platformio device list` if it has changed. The firmware replaces the previously installed SAMD21 pressure + dual IMU firmware (source remains available in `hardware/sensorhub/pressure-imu/`); this test is easily reversible by reflashing it.

## Confirmed hardware result — 2026-11-17

User tested the dedicated SAMD21 VL6180X firmware (ToF physically A2) using COM3 at 115200 baud. On pressing `s` in the Serial Monitor, the firmware reported:

```text
# TOF_A1 address=0x29 ack=1
# TOF_MODEL_ID value=0xB4 expected=0xB4 identified=1
```

**Result: PASS** — MCP-free, isolated VL6180X identification on SAMD21 Sensor A2, including I²C address acknowledgement and expected model-ID read. This test did **not** initialize ranging or confirm distance measurements. It does not establish the STM32 pressure module's power or wiring.

## Example output (now observed on physical hardware)

```text
# KEVIN SAMD21 TOF VL6180X A1 READ-ONLY ID v0.1
# TOF_A1 address=0x29 ack=1
# TOF_MODEL_ID value=0xB4 expected=0xB4 identified=1
```

If `ack=0`: device did not answer; investigate voltage, cable, orientation and bus. If `ack=1` but ID is wrong, another I2C device (such as BHI360) may be at address 0x29, or register read failed. Send `s` through serial monitor to repeat. If identity passes, the next step is a separate VL6180X initialization/ranging implementation.

**Correction recorded 2026-11-17:** User confirmed the ToF was **physically connected to A2**, NOT A1, for this successful read-only test. Earlier source banners and the Git branch name mention A1; those labels did not establish where the plug was connected. The I2C pin assignment PA16/PA17 / SERCOM1 is unchanged.
