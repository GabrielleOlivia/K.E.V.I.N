# K.E.V.I.N. — SAMD21 Pressure A2 + VL6180X ToF B1

**Status: Firmware compiled and run on physical hardware on 2026-11-17. Initial combined bench test: both sensor addresses NACKed (not yet working).**

## Why this arrangement

Two working individual tests are now combined, but **on separate SAMD21 I2C buses**:

| Sensor | Carrier socket | I2C bus | SAMD21 pins | I2C 7-bit address |
| --- | --- | --- | --- | --- |
| MCP3426 pressure ADC (SimModule Pressure v2) | **A2** | SERCOM1 / Sensor A | PA16 SDA (variant index 11), PA17 SCL (13) | **0x68** |
| VL6180X ToF (red board) | **B1** | SERCOM2 / Sensor B | PA12 SDA (variant index 28), PA13 SCL (39) | **0x29** |

Both SERCOM buses run at 100 kHz. Pressure ADC readings were previously physically tested on **A2** with the proper four-conductor cable; VL6180X identification and live raw distances were previously confirmed on **A2** (same Sensor A I2C bus), not yet B1. The wiring and supply on B1 must be verified prior to plugging in the ToF.

The head BHI360 previously used B1 and has the same 0x29 address as the ToF. **Remove both IMUs** during this test. Do not test this firmware with the head IMU or any other unknown device at B1 0x29.

## Physical hookup

1. Close all Serial Monitors and **unplug USB** from SAMD21.
2. Keep the already verified **pressure MCP3426 module on A2**, using its proper intact four-contact connector (not individual jumper wires).
3. Move **only the VL6180X ToF** to **B1**, using a connector verified to correctly map **GND, 3.3 V, SDA, and SCL**. Check orientation; a mechanical four-pin fit is not a pinout guarantee. If B1 supply and signal arrangement are uncertain, use a multimeter and an actual board drawing before connecting power.
4. Leave the other A-side port and both IMUs disconnected. Reconnect USB only when electrical pin/voltage compatibility is confirmed.

**Pressure caveat:** A live MCP3426 ADC reading does not prove that an MPXV5010GP pressure transducer has its specified supply (nominal 5 V). These ADC values are **uncalibrated**. Never inject 5 V onto SAMD21 3.3 V or SDA/SCL pins. Do not use this for infant/patient measurements.

## Build and upload on Windows

```powershell
cd "$env:USERPROFILE\Documents\K.E.V.I.N"
git fetch origin
git switch --track origin/feature/samd21-pressure-a2-tof-b1-live
cd .\hardware\sensorhub\samd21-pressure-a2-tof-b1
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run
```

After a successful build and safe physical hookup (and with Serial Monitor **closed**):

```powershell
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run -t upload --upload-port COM3
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" device monitor -p COM3 -b 115200 -f send_on_enter
```

Use `platformio device list` if COM3 changed due to SAMD21 bootloader enumeration. Upload overwrites the flashed live ToF firmware (which was tested on physical A2 despite an A1 banner) but both projects remain intact in source branches.

## Expected output (example format, not measured yet)

```text
# KEVIN SAMD21 PRESSURE A2 + VL6180X TOF B1 v0.1
# PRESSURE_PRESENT A2 0x68
# TOF_MODEL_ID value=0xB4 expected=0xB4 identified=1
# TOF_READY B1 live ranging
# STATUS pressure_A2_ack=1 tof_B1_ack=1 tof_initialized=1
# pressure,t_ms=4568,raw_adc=2505,valid=1,pressure_calibrated=0
# tof,t_ms=4609,raw_mm=48,err=0,valid=1
```

These numbers are **illustrative**, not recorded. Sampling targets around 4 Hz for each sensor, with the pressure ADC's one-shot conversion handled **non-blockingly** to avoid holding up the ToF bus.

- **Pressure:** `raw_adc` is raw ADC count, `valid=1` only when conversion status and returned configuration agree. `pressure_calibrated=0` at all times; no zeroing or kPa/hPa conversion.
- **ToF:** `raw_mm` is the raw distance. Only accept it when **`err=0,valid=1`**. `raw_mm=255,valid=0` is not a real distance; use an opaque white target 30–100 mm from the sensor.
- **I2C identity:** `pressure_A2_ack=1` means the ADC answered address 0x68 on bus A. For ToF, `identified=1` additionally verifies the VL6180X model ID `0xB4`.

Commands in serial monitor:
- `s` — report pressure A2 and ToF B1 I2C ACK status
- `p` — pause or resume sensor sampling
- `h` — help

Missing pressure does **not** prevent ToF measurements. Failed ToF initialization does **not** stop pressure ADC measurements. If a device fails, its own bus is retried about every 2 s (do **not** hotplug to force reconnect).

## Evidence and next milestones

Previously verified:
- SAMD21 A2 pressure raw ADC (when using original correct four-wire cable)
- SAMD21 A2 VL6180X with model ID 0xB4 and live 9–192 mm valid raw samples
- STM32 upper Port A VL6180X with live distance measurements

**New two-sensor test on SAMD21 A2/B1: pending.** Next: compile, upload, record simultaneous raw streams, then run fixed-distance ToF stability and pressure response tests only after confirming transducer supply. This is a prototype simulator, not a medical device.

## Actual initial combined test — 2026-11-17

The user uploaded the combined firmware and observed repeated `# PRESSURE_ABSENT A2 0x68` and `# TOF_ABSENT B1 0x29` on COM3. Neither device acknowledged in this combination. After testing, the user clarified **the previously successful VL6180X identification and live-range experiments were physically connected to A2**, not A1 as earlier written. Both devices therefore have separate known-working *individual* A2 histories, while ToF on B1 is unverified.

**Next controlled test:** USB power off, remove the ToF from B1, leave pressure on A2, USB power on; send `s` to check `pressure_A2_ack` independently. This isolates whether connecting the B1 device contributes to the pressure problem. Do not infer damage or insufficient voltage solely from NACKs.

### Controlled ToF-disconnected repeat — 2026-11-17

With the **ToF unplugged from B1**, the user reran the combined firmware on SAMD21 COM3. The logs showed:

```text
# PRESSURE_ABSENT A2 0x68
# TOF_ABSENT B1 0x29
# STATUS pressure_A2_ack=0 tof_B1_ack=0 tof_initialized=0
```

Thus the pressure ADC still NACKs at 0x68 in this firmware with B1 physically empty; a ToF-driven conflict is **not a sufficient explanation**. Next discriminating test: keep the same A2 pressure-only hookup and flash previously working `feature/pressure-imu-integration`, `hardware/sensorhub/pressure-imu`, then send `s` and check `# BUS_CHECK bus=A device=PRESSURE_ADC address=0x68 wire_status=0 ack=1`. If old firmware works, debug new firmware; if old firmware also NACKs, troubleshoot live sensor-side 3.3 V/GND, connector orientation/pin contacts, and continuity.

### Historical pressure-only firmware check — 2026-11-17

The user disconnected ToF and flashed what was intended to be the earlier `hardware/sensorhub/pressure-imu` firmware. On COM3, the observed startup banner was `# KEVIN PRESSURE + DUAL IMU v0.3 OPTIONAL-PRESSURE (no BHI firmware writes)`; `# BUS_CHECK bus=A device=PRESSURE_ADC address=0x68 wire_status=2 ack=0` repeated, and pressure samples were suppressed as `PRESSURE_ABSENT`.

**Critical version qualification:** GitHub's `feature/pressure-imu-integration` currently has a `v0.4 LINK-STABILITY` startup banner, *not* the observed `v0.3 OPTIONAL-PRESSURE`. Thus this serial run does not independently verify that the intended branch's newest firmware was uploaded; check `git branch --show-current` and the `Serial.println` banner in the local source, then verify PlatformIO upload SUCCESS. I2C `wire_status=2` is an address NACK, not a calibrated reading; the physical reason remains unresolved.
