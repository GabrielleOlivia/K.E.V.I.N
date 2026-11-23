# K.E.V.I.N. four physical sensor integration — experimental v0.3

**Status: source code prepared; combined firmware has NOT been compiled on the user's PC or tested with all four sensors.** Isolated B2 IMU was tested successfully; the reported loose B2 wires caused intermittent read failures. Fix those connections BEFORE connecting the full array or uploading firmware.

## Connector assignments

| Physical port | Device | Internal bus | 7-bit I2C address |
|---|---|---|---|
| A1 | Head BHI360 + BMM350 IMU | Bus A, SERCOM1 PA16/PA17 | BHI 0x29, BMM 0x15 |
| A2 | MCP3426 pressure ADC | Bus A, SERCOM1 PA16/PA17 | 0x68 |
| B1 | VL6180X ToF | Bus B, SERCOM2 PA12/PA13 | 0x29 |
| B2 | Chest BHI360 + BMM350 IMU | Bus B, SERCOM2 PA12/PA13 | BHI 0x28, BMM 0x14 |

These are PHYSICAL connectors; legacy serial output calls the buses A2 and B2 even if a sensor is on a different physical connector. B1 0x29 and A1 0x29 do not collide because they are on separate I2C buses. The B1 ToF and B2 IMU are on the SAME bus but use distinct addresses.

**Electrical safety:** Disconnect USB and ALL other power before connecting or fixing wiring. Use properly crimped connectors and strain relief, not loose Dupont jumpers that disconnect when tilted. Double-check actual PCB pinout and 3.3 V, ground, SDA, SCL. The archived B2 connector may include a fifth VSYS/5 V pin: do NOT shift a four-wire connector or put 5 V into a non-5-V-tolerant IMU. Do not use on an actual patient.

## Windows setup — separate Git worktree

Run from your EXISTING repo worktree:

    cd "$env:USERPROFILE\Documents\KEVIN-a2-b2-review"
    git fetch origin
    git worktree add -b kevin-four "$env:USERPROFILE\Documents\KEVIN-Four" origin/feature/four-sensor-live-integration-2026-11-23
    cd "$env:USERPROFILE\Documents\KEVIN-Four\hardware\sensorhub\samd21-pressure-a2-tof-b2"
    $pio = "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe"
    py -3 scripts/vendor_bhi360_four.py
    & $pio run -e kevin_four_sensors

The LAST command only BUILDS the experimental image. STOP if any compiler, linker, flash or RAM failure occurs. The installer downloads official Bosch SDK sources and applies the previously tested PlatformIO compatibility changes; it does not flash the board. The original default scanner main.cpp is preserved.

## Opt-in upload only after build PASS and wiring verification

Close all serial monitor and simulator sessions first:

    & $pio run -e kevin_four_sensors -t upload --upload-port COM3
    & $pio device monitor -p COM3 -b 115200 -f send_on_enter -f log2file

Enter one command at a time in the monitor:

1. c = select both buses; stop if pinmap, pinmux or idle-line failures
2. i = scan Bus A and Bus B. Expect A 0x15, 0x29, 0x68; B 0x14, 0x28, 0x29. Exactly three each
3. i = repeat identical full scan, expect FOUR_SCAN_OK consecutive=2
4. s = verify both BHI360/BMM350 identity registers; expect FOUR_IMU_IDS_OK
5. m = initialize both BHI360s in sequence and start independent head/chest XYZ accelerometer streams. This writes Bosch firmware into each sensor RAM, NOT the SAMD21 program flash
6. g = start pressure ADC and ToF measurements; observe valid lines from ALL FOUR modules, interleaved

Both IMUs must output valid ACCEL frames with sensor=head and sensor=chest. Pressure output begins pressure, and ToF output begins tof. Never take printed IMU_READY alone as evidence of movement sensing.

**If a sensor drops out or IMU_FAULT appears, STOP.** Do not keep sending m with loose wires. Save the log, disconnect power before handling the assembly.

## Updated desktop simulator

Close PlatformIO monitor with Ctrl+C; COM3 cannot be used by both at once.

    cd "$env:USERPROFILE\Documents\KEVIN-Four\software\kevin_patient_simulator"
    py -3 -m pip install pyserial
    py -3 -m unittest discover -s tests -v
    py -3 app.py

Choose SENSOR-REACTIVE, Real SensorHub COM3, Connect COM, Select c, Scan i twice, Status s, Boot BOTH IMUs (m), then Acquire g. Place the head and chest IMUs in their intended neutral mount positions, wait for fresh XYZ samples, and click ZERO head/chest. Relative head-versus-chest gravity tilt drives an ILLUSTRATIVE airway obstruction model. Choose pitch or roll and invert either sign as necessary for your mount; re-zero after any such change. Check that tilting the whole manikin together does not significantly alter the relative reading.

Pressure ADC pulses are treated as breath-pressure proxies, NOT as measured air volume. ToF displacement is a hand/CPR-motion proxy, NOT clinical compression depth. HR/SpO2/RR/EtCO2 are synthetic teaching data. If either IMU becomes unavailable, the simulator holds the physiology rather than replacing missing tilt with zero. Manual fallback exists as an explicitly labelled optional override, OFF by default.

## Current validation checklist

- [ ] Loose B2 connector repaired and pinout/rails checked with power removed
- [ ] PC four-sensor firmware build passes
- [ ] Two consecutive complete six-address I2C scans pass with four modules
- [ ] Both IMU pairs report expected chip ID and stream live XYZ while moving
- [ ] Pressure and ToF stream valid data simultaneously with both IMUs
- [ ] No I2C faults or USB disconnects during a 30–60 second stationary/tilt session
- [ ] Both IMUs rigidly mounted, zero reference and pitch/roll sign checked
- [ ] Simulator independently responds to head tilt, pressure breaths and hand/ToF motion

## Rollback

The proven default scanner remains in the old project. After closing COM3 and verifying the correct board:

    cd "$env:USERPROFILE\Documents\KEVIN-a2-b2-review\hardware\sensorhub\samd21-pressure-a2-tof-b2"
    & "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run -e adafruit_feather_m0_express -t upload --upload-port COM3

Do NOT send the old scanner command g while its B port contains an IMU instead of the VL6180X.
