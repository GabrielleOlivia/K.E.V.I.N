# K.E.V.I.N. — Combined STM32F405 Pressure + VL6180X ToF

**Status: prepared in GitHub; not yet built on the user's machine, not flashed, not hardware-tested.**

This project combines the two separate sensor projects in one STM32 firmware image:

- Pressure: MCP3426 ADC at I2C address **0x68**, with the CH1 one-shot 16-bit setting **0x88**, adapted from the SAMD21 pressure project.
- ToF: VL6180X at I2C address **0x29**, with expected model ID **0xB4**, using the teammate's driver and initialization routine.
- Both can share one I2C bus because their addresses differ, provided power, levels and wiring are compatible; this revision retains the ToF on the proven Port A upper I2C1 connection and tentatively places pressure on Port B I2C2.

## Sources

- ToF driver: https://github.com/OlympusSixtems/KEVIN/blob/feature/stm32f405-vl6180x-tof-probe/firmware/tof_probe_f405/include/vl6180x.h
- Teammate's STM32 ToF project: https://github.com/OlympusSixtems/KEVIN/tree/feature/stm32f405-vl6180x-tof-probe/firmware/tof_probe_f405
- Pressure prototype: https://github.com/GabrielleOlivia/K.E.V.I.N/blob/feature/pressure-imu-integration/hardware/sensorhub/pressure-imu/src/main.cpp

## New bench preflight: pressure PCB identity unresolved (2026-11-17)

**Do not enable Port B power or flash the enabled two-sensor build yet.** Inspection of the newly uploaded `MonitorHW(4).zip` found the old Eagle `Pressure_Module_v2.1_jan2024.sch`. That design uses an **MP3V5050** pressure transducer, an **MCP3426** ADC (IC2) and a **FOUR-pin** PTSM I2C connector.

The current physical pressure PCB photograph instead shows a part marking starting **MPXV70…** and a **FIVE-wire** connection to the STM32 Port B. This is a **different revision/design**, so the old MCP3426/0x68 data cannot establish the current PCB's electronics. The MPXV70xx *sensor IC* has an analog output; there **may** be an ADC elsewhere on the PCB (including the reverse side). Verify the new PCB backside and any IC2 / MCP3426 markings before assuming I2C.

The current SensorHub v1.1.0b KiCad PCB shows Port B U$59 pads P1=5V, P2=GND, P3=3.3V_OUT1, P4=SCL2, P5=SDA2. **The photographed physical carrier is v1.0.3.** Its Port B P1–P5 assignments and jumper colors were not verified. Do not infer these from the newer revision.

The fifth wire is *consistent with* a sensor needing both 5 V (analog pressure chip) and switched 3.3 V (digital converter), but **that is a hypothesis, not evidence**. A bare MPXV70xx analog output cannot be read as MCP3426 I2C data. Never wire such an analog output directly to an STM32 3.3V-only GPIO without verifying its voltage and the appropriate signal conditioning.

**Already passing:** original STM32 `tof_probe_f405 v0.2`, ToF plugged into Port A upper, valid=1 err=0, raw distances 44–62 mm, roughly 10Hz. Preserve this functional baseline while inspecting the pressure module. Full current MCU flash is backed up in two identical local files.

**First safe test today:** USB power OFF; inspect the current pressure PCB front/reverse for ADC IC markings, labeled pads and wire-to-pin assignments. No software or flash change needed. Then choose either MCP3426 I2C scanner or a properly protected analog ADC input test.

## Hardware safety: board revision differs

The physical carrier in the supplied photo is RobotPatient SensorHub MicroMod **v1.0.3 (Feb 2025)**. The teammate's pin and power mapping comes from a **v1.1.0b** schematic. **New bench evidence (2026-11-17): ToF physically plugged into the Port A upper socket works under original firmware (`tof_probe_f405 v0.2`) using PB7/PB6 and PC9, yielding repeated `err=0,valid=1` distance values 44–62 mm.** This validates the existing ToF path functionally but does NOT independently verify the Port B pressure socket or its supply/voltage compatibility.

By default platformio.ini sets **KEVIN_SENSOR_IO_ENABLED=0**. When running this default firmware, it only prints a USB heartbeat: it does NOT drive the sensor rails, initialize I2C, scan, or perform conversions.

**Tentative v1.1.0b reference only — do NOT wire according to this without verifying the v1.0.3 PCB:**

| Sensor | Tentative location | I2C bus | Tentative STM32 SDA/SCL | Tentative 3.3V rail switch |
|---|---|---|---|---|
| Pressure MCP3426 0x68 | Port B (proposed, **NOT physically verified**) | I2C2 | PB11/PB10 | PC8/G3 |
| ToF VL6180X 0x29 | Port A upper (**physically functioning with original firmware**) | I2C1 | PB7/PB6 | PC9/G4 |

Verify every connector pin and output rail against the **actual v1.0.3** schematic or lab electrical measurements. Check supply voltage, common ground, I2C pullups, sensor cable pin order, and breakout electronics.

The *bare* VL6180X IC needs a supply around 2.8V, so a 3.3V supply is safe only if the actual ToF **breakout** is designed to tolerate it. The physical pressure transducer may require a different supply from the MCP3426 ADC side. Do not connect raw 5V signal/power to STM32 3.3V pins.

If a BHI360 is assigned to the same bus as the ToF, both default to address 0x29 and will conflict. That conflict does not affect this two-sensor pressure+ToF stage.

## Build only

From the K.E.V.I.N. repository, in VS Code PowerShell:

    git fetch origin
    git switch --track origin/feature/stm32f405-pressure-tof-integration
    cd hardware\sensorhub\stm32f405-pressure-tof
    & "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run

If you are already tracking the branch, use git pull --ff-only instead of git switch --track.

Expected when the code compiles: PlatformIO prints [SUCCESS]. **Do not use upload yet** — the default firmware intentionally has no sensor I/O and would replace the current program needlessly.

## Enabling hardware later — not yet approved

Only after verifying the v1.0.3 connector pins, switched rails, ToF breakout voltage and pressure ADC/transducer wiring, review/edit the tentative kPressureRail, kTofRail, TwoWire buses in src/main.cpp and opt into the following flags in platformio.ini:

    -D KEVIN_SENSOR_IO_ENABLED=1
    -D KEVIN_CARRIER_V103_PINMAP_VERIFIED=1
    -D KEVIN_SENSOR_SUPPLIES_VERIFIED=1

The second and third flags are manual safety declarations, **not proof**. Never enable them without validating physical wiring, and agree on DFU upload/restore with the team before replacing original firmware.

## Intended serial output

The following is example format only — NO sensor readings on this STM32 have been observed yet:

    # STATUS pressure_ack=1 tof_ack=1
    # PRESSURE_ADC_PRESENT send z for zero calibration
    # TOF_READY VL6180X; raw distance only
    # pressure,t_ms=1250,raw_adc=2538,baseline_adc=,delta_adc=,calibrating=0,candidate_count=0,valid=1
    # CALIBRATION_OK baseline_adc=2535
    # pressure,t_ms=8500,raw_adc=2541,baseline_adc=2535,delta_adc=6,calibrating=0,candidate_count=0,valid=1
    # tof,t_ms=8550,raw_mm=57,err=0,valid=1

Commands: **s** = read I2C acknowledgements; **z** = calibrate pressure zero while at rest (30 valid samples, max 45 attempts and max 80-count spread); **h** = help.

The ADC conversion is split into start/read stages so ToF sampling can occur while the ADC converts. ToF calls may block up to 100 ms. Nominal polling is ~4 Hz each, best effort, not real-time.

All messages start with #; no CSV pressure protocol compatibility is claimed yet. This is a bench diagnostic, not the Raspberry Pi app or a medical device.

Raw ADC counts are NOT calibrated airway pressure, flow or tidal volume. Raw ToF millimetres are NOT validated CPR compression depth.

## Preserve original firmware

The current 1MB STM32 flash image was saved to two identical local files (SHA-256: 6B82744EEB03B948B784AC3F73664F6AB2F2FCC75F9837E5994AD0DEA32B2FCF). Restore has NOT been tested. Never commit the .bin backup into Git.

## Suggested next checks

1. Retain the working ToF on Port A upper. Verify the v1.0.3 Port B connector pinout, switched rail and pressure board voltage independently; the ToF path alone does not prove Port B is safe.
2. Photograph/identify the MCP3426 pressure ADC module and VL6180X ToF breakout; verify their acceptable power levels.
3. Build this firmware on the user's existing PlatformIO STM32 toolchain. Do not upload.
4. After electrical validation and team approval, enable sensor I/O, rebuild, then test pressure ACK, raw ADC samples, ToF ID and raw ranging together.
