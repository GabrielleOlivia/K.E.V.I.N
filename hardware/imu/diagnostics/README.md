# K.E.V.I.N. — BHI360 ID probe (diagnostic stage 1)

**What this is:** Standalone PlatformIO project for the existing custom SAMD21 SensorHub, using the previously proven Adafruit Feather M0 Express variant. It checks I2C connectivity to the existing pressure ADC and the two possible Bosch BHI360 I2C addresses, then reads the BHI360 Fuser2 identifier and optional revision and boot-status registers. All reads are non-destructive; no BHI360 firmware upload, reset, patient simulation, sensor fusion, or actual pressure sampling occurs.

**What this is not:** A physical IMU driver, angle sensor, or proof of safe electrical compatibility. No hardware has been tested with this project yet. The RobotPatient BMM/BHI 9DoF Sensor board revisions photographed (1.1.0B and 1.2.0a) have no verified electrical connector schematic in the provided professor ZIP. In particular Bosch's bare BHI360 works at 1.8 V; do NOT assume the unknown breakout accepts 3.3-V power and logic. Never guess the black/red/blue/yellow wire assignments from color. The professor's v1.2.5 SensorHub schematic is NOT proof of v1.2.2 wiring.

## Bus mapping and limits

From the **Feather M0 Express Arduino variant**:

| Logical bus | SAMD21 pins | Variant indices | Reference SensorHub connectors | Notes |
|---|---|---|---|---|
| A | PA16 SDA, PA17 SCL | 11, 13 | A1/A2 | Sensor A2 pressure wiring previously verified |
| B | PA12 SDA, PA13 SCL | 28, 39 | B1/B2 | From newer hub reference, **not yet validated on actual v1.2.2 board** |

The firmware checks variant indices against expected MCU pads before touching the bus. It uses 100 kHz on both. It tests known addresses by default (A: `0x68` for MCP3426 pressure ADC, A/B: `0x28` and `0x29` for BHI360). A full optional scan is available. If the pressure sensor ACKs, that checks only the I2C device address, **not pressure acquisition**. If two same-address IMUs are attached to the same bus, they cannot be distinguished.

## Before connecting an IMU

1. Keep the pressure sensor on its established A2 connection. **Power the SensorHub off before attaching/removing any module.**
2. Obtain pinout evidence for the actual RobotPatient breakout revisions or a continuity/voltage assessment by a qualified supervisor. Check VCC, GND, SDA, SCL, pull-up voltage and any level shifting. The four-wire plug cannot safely be wired by color alone.
3. Verify the actual SensorHub v1.2.2 B connector rail and SDA/SCL routing with its schematic or continuity testing. The available v1.2.5 schematic is only a reference.
4. Only after electrical approval, connect ONE IMU to a verified I2C connector. Do not connect both yet.

## Build/upload using VS Code with PlatformIO

Open this folder (the one that contains **this** `platformio.ini`) as its own PlatformIO project. This is not the root project's existing pressure firmware. Stop PlatformIO Serial Monitor before uploading.

1. Connect SensorHub through USB. This is safe to do with **no IMU connected**.
2. PlatformIO **Build**, then **Upload** (this replaces the program currently flashed on the MCU temporarily; the earlier pressure firmware remains saved in the Git repo).
3. Open serial monitor at **115200** baud. If using the PlatformIO terminal: `pio device monitor --baud 115200`.
4. The app prints its banner, then repeats its probe every 5 seconds. Sending `p` runs an immediate probe; `s` performs a full bus scan; `h` shows help. In some terminal monitors, typing `p` doesn't transmit until you press Enter.
5. Save the output and share the lines from `# PROBE_BEGIN` to `# PROBE_END`.

Example *illustrative only* output, NOT a reading from your board:

```text
# KEVIN_BHI360_ID_PROBE v0.1
# PINMAP_OK A=PA16/PA17 (SERCOM1), B=PA12/PA13 (SERCOM2)
# PROBE_BEGIN t_ms=4123
# Bus A pressure ADC 0x68 ACK (not a pressure measurement)
# A BHI candidate 0x28 NO_ACK
# A BHI candidate 0x29 NO_ACK
# B BHI candidate 0x28 ACK FUSER2_ID=0x89 BHI360_IDENTIFIED REV=0x02 BOOT_STATUS=0x01 (identification only; fusion not enabled)
# B BHI candidate 0x29 NO_ACK
# PROBE_END
```

If the B bus is empty, BHI candidate lines should show `NO_ACK`. If `PINMAP_MISMATCH`, **do not try alternate indices by guessing**. If an address ACKs but the ID differs, the device is not confirmed as BHI360. If you see repeated I2C lock-ups, power off and inspect wiring/rails, don't keep resetting.

Host-only log parser (optional): `python -m tools.parse_probe path/to/saved_log.txt`.
Host parser tests: `python -m unittest discover -s tests -v`.

## Integration after successful hardware ID

Use the official Bosch BHI360 SensorAPI to initialize the correct firmware, enable a game rotation vector (6-axis) or suitable 9-axis firmware after confirming BMM350 connection, and read FIFO events. Implement nonblocking acquisition and publish host messages using the existing integration protocol. Keep original pressure firmware and add the IMU driver to a *new, combined* SensorHub firmware application only after per-module hardware validation. Don't treat the Fuser2 ID as an orientation reading.

References:
- Bosch BHI360 datasheet: https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bhi360-ds000.pdf
- Bosch BHI360 SensorAPI: https://github.com/boschsensortec/BHI360_SensorAPI
- Adafruit Feather M0 Express variant: https://github.com/adafruit/ArduinoCore-samd/blob/master/variants/feather_m0_express/variant.cpp
