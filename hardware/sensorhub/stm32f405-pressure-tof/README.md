# K.E.V.I.N. — Combined STM32F405 Pressure + VL6180X ToF

## LIVE BENCH RUNBOOK — STM32F405, pressure + ToF (2026-11-17)

This **separate test branch** enables both sensors in `platformio.ini`:

```ini
-D KEVIN_TOF_IO_ENABLED=1
-D KEVIN_PRESSURE_IO_ENABLED=1
-D KEVIN_CARRIER_V103_PORT_B_VERIFIED=1
-D KEVIN_PRESSURE_INTERFACE_VERIFIED=1
```

These last two flags record **the user's report** that the hardware connections were checked; the code cannot independently measure or certify power compatibility. This runbook applies **only if** they checked the actual v1.0.3 Port B **physical 5-pin mapping**, common ground, **MPXV5010GP transducer's specified 4.75–5.25V**, pressure module MCP3426 supply, and **I2C SDA/SCL logic voltages compatible with STM32 3.3V pins**. If any voltage was *not* checked, do **not** power the pressure module until measured/confirmed. Do not infer safety from matching jumper colors.

- **ToF** remains on the *physically proven* Port A upper (PB7/PB6, PC9 rail switch), 0x29.
- **Pressure** is mapped to Port B (PB11/PB10, PC8 3.3V logic rail switch), MCP3426 0x68. Physical pin assignment and 5V transducer feed depend on the verified user's connection.

### Build and upload

```powershell
cd "$env:USERPROFILE\Documents\K.E.V.I.N"
git status --short
git fetch origin
git switch --track origin/feature/stm32f405-pressure-tof-live-bench
cd .\hardware\sensorhub\stm32f405-pressure-tof
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run
```

If local branch already exists, use `git switch feature/stm32f405-pressure-tof-live-bench` followed by `git pull --ff-only`. Check that the build ends `[SUCCESS]`. No code was compiled in the GitHub connector.

Confirm original backup remains outside Git in two matching files, 1,048,576 bytes, SHA-256 `6B82744EEB03B948B784AC3F73664F6AB2F2FCC75F9837E5994AD0DEA32B2FCF`. The backup was read and hashed, **not restore-tested**.

**Only with power/signal checks complete and wiring stable:** close Serial Monitor; connect USB, hold BOOT and tap RST, release BOOT, connect USB in STM32CubeProgrammer. Select:

```text
C:\Users\olivi\Documents\K.E.V.I.N\hardware\sensorhub\stm32f405-pressure-tof\.pio\build\micromod_f405_pressure_tof\firmware.bin
```

Program with address `0x08000000` and verification enabled. No full-chip erase, option-byte changes or unnecessary mass erase. After programming, reset without BOOT, check `pio device list`, open monitor at 115200 baud, e.g.:

```powershell
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" device monitor -p COM9 -b 115200 -f send_on_enter
```

Serial port COM9 may change after reset.

### Pass/fail checkpoints

1. With no pressure applied, type `s` and Enter to request:
   `# STATUS pressure_ack=1 tof_ack=1`.
   Presence proves only I2C acknowledgement, not valid sensing.
2. Look for actual `# pressure,t_ms=...,raw_adc=...,valid=1` (approximately every 250 ms) and `# tof,t_ms=...,raw_mm=...,err=0,valid=1` with a flat matte target ~50mm from ToF. `err=6/7/11,valid=0` is invalid ranging, NOT a distance.
3. With pressure at rest, type `z` Enter to zero-calibrate 30 ADC samples; look for `# CALIBRATION_OK baseline_adc=...`. Do not apply pressure during calibration.
4. Then apply/release gentle syringe pressure; expect `delta_adc` changes, and (if threshold crossed) `# PRESSURE_POSITIVE_START` then `# PRESSURE_POSITIVE_END`. ToF samples must continue.
5. If `pressure_ack=0`, check `# PRESSURE_ADC_ABSENT address 0x68 on I2C2`. Turn USB OFF before manipulating any wires, and retain the complete log. A startup NACK may recover automatically after about 2 sec. **No pressure zeros should be fabricated.**
6. **Stop immediately** if the circuit becomes unusually hot, smells abnormal, USB disconnects repeatedly, or there are any signs of a short. Do not retry blindly.

Raw ADC counts are **not calibrated pressure, airflow, air volume or breaths**. ToF `raw_mm` are raw range, not validated CPR compression depth. Both sensors passing means communications and bench response, not medical validity.

### Next integration

After simultaneous pressure+ToF data passes, add BHI360 head/chest sensors through an I2C address/port plan. At least three devices default to 0x29 (ToF, two BHI360s), so allocate addresses or bus isolation before connecting all simultaneously. BHI360 identification is not yet evidence that sensor firmware, fusion or neck-angle readings work.

---


**Status: combined firmware build succeeded on user's Windows toolchain; not flashed or hardware-tested as a combined program.** The existing original ToF-only firmware produced real valid ranging data on the physical STM32.

This project combines the two separate sensor projects in one STM32 firmware image:

- Pressure: MCP3426 ADC at I2C address **0x68**, with the CH1 one-shot 16-bit setting **0x88**, adapted from the SAMD21 pressure project.
- ToF: VL6180X at I2C address **0x29**, with expected model ID **0xB4**, using the teammate's driver and initialization routine.
- Both can share one I2C bus because their addresses differ, provided power, levels and wiring are compatible; this revision retains the ToF on the proven Port A upper I2C1 connection and tentatively places pressure on Port B I2C2.

## Sources

- ToF driver: https://github.com/OlympusSixtems/KEVIN/blob/feature/stm32f405-vl6180x-tof-probe/firmware/tof_probe_f405/include/vl6180x.h
- Teammate's STM32 ToF project: https://github.com/OlympusSixtems/KEVIN/tree/feature/stm32f405-vl6180x-tof-probe/firmware/tof_probe_f405
- Pressure prototype: https://github.com/GabrielleOlivia/K.E.V.I.N/blob/feature/pressure-imu-integration/hardware/sensorhub/pressure-imu/src/main.cpp

## Current pressure PCB identified from 2026-11-17 photos

**Confirmed visually:** The actual pressure sensor IC is marked **MPXV5010GP**, and the red PCB's reverse silkscreen reads **SimModule Pressure v2.0.0 Jan 2026**. A small 8-pin IC at designator **IC2** is present on the PCB, consistent with the **MCP3426 ADC** in the repository's documented v2.0 pressure setup. The small IC's actual part marking is not legible in the supplied photo, so confirm its identity by read-only I2C ID/ACK once wiring has been verified. The sensor PCB rear shows **four connector through-hole solder joints**, not five; do not assume each visible colored jumper is an independently connected signal.

**Version-specific caution:** The `MonitorHW(4).zip` pressure schematic `Pressure_Module_v2.1_jan2024.sch` refers to an earlier/different MP3V5050 sensor and four-pin I2C design. It does not by itself establish voltage/pin order for the actual v2.0 Jan 2026 board. The current pressure system was previously bench-tested on the SAMD21 with MCP3426 at **0x68**, config **0x88**, producing raw counts; using STM32 Port B is a new untested wiring configuration.

The new STM32 photo shows a v1.0.3 (Feb 2025) carrier. The separately supplied v1.1.0b PCB maps Port B as **P1=5V, P2=GND, P3=3.3V_OUT1, P4=SCL2, P5=SDA2** and power GPIO **PC8/G3**. This mapping is **not independently verified** on the v1.0.3 carrier; the pressure PCB's **four contacts** also must not be mapped to the carrier's **five contacts** solely by wire colors. Check both mating pin orders and module supply compatibility before applying power. Unpowered continuity verification or correct v1.0.3/v2.0 PCB design data is preferred. Do not bridge 5V to a 3.3V rail or I2C line.

**Already working on physical STM32:** original `tof_probe_f405 v0.2` with ToF on Port A upper, I2C1 PB7/PB6, PC9 rail control, yielding valid=1, err=0, raw distances 44-62 mm. Keep this firmware and wiring as the functional regression baseline until Port B is verified. Existing STM32 flash was backed up to two equal SHA-256 local copies.

## Current planned physical regression test (ToF only)

1. **Disconnect STM32 USB power and completely unplug the unverified pressure sensor jumper harness from the SensorHub**. Avoid loose powered jumper ends. Leave the keyed, demonstrated ToF cable on Port A upper.
2. Build the new firmware with `KEVIN_TOF_IO_ENABLED=1` and `KEVIN_PRESSURE_IO_ENABLED=0`. Review these flags: pressure must read **0**.
3. Verify the original image still exists in the two local `KEVIN_STM32_original_backup.bin` copies. These were SHA-256 equal but restore has not been tested.
4. To deploy if team-approved, use STM32CubeProgrammer **USB DFU bootloader** (hold BOOT, tap RESET, release BOOT), choose the built **.pio/build/micromod_f405_pressure_tof/firmware.bin**, start **0x08000000**, download/verify, then reset to run. Only the active ToF rail PC9 is toggled.
5. Open PlatformIO Serial Monitor at the enumerated COM port. Expect `# PRESSURE_IO_DISABLED Port B untouched`, `# TOF_READY VL6180X; raw distance only`, and `# tof,...,err=0,valid=1` for a white target ~5 cm away.
6. If no ToF samples, disconnect USB and preserve the serial output. Do **not** attempt Port B pressure wiring until source pin mapping verified.

This is a deliberate temporary regression test, **not** simultaneous pressure+ToF validation. After it passes, the next hardware task is confirm pressure v2.0 connector pin assignments against STM32 v1.0.3 Port B; only then enable pressure and sample both devices.

## Hardware safety: board revision differs

The physical carrier in the supplied photo is RobotPatient SensorHub MicroMod **v1.0.3 (Feb 2025)**. The teammate's pin and power mapping comes from a **v1.1.0b** schematic. **New bench evidence (2026-11-17): ToF physically plugged into the Port A upper socket works under original firmware (`tof_probe_f405 v0.2`) using PB7/PB6 and PC9, yielding repeated `err=0,valid=1` distance values 44–62 mm.** This validates the existing ToF path functionally but does NOT independently verify the Port B pressure socket or its supply/voltage compatibility.

**Current first regression-test default (2026-11-17):** `KEVIN_TOF_IO_ENABLED=1` and `KEVIN_PRESSURE_IO_ENABLED=0`. This activates ONLY the already demonstrated ToF port A upper (PB7/PB6 and PC9) and does **not** configure the pressure I2C2 bus or toggle pressure rail PC8. **Disconnect every pressure jumper with USB power OFF before using this firmware.** The previous `KEVIN_SENSOR_IO_ENABLED` flag has been replaced by independent device flags. The previous USB-only build may be recovered by setting both flags to 0.

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

Expected when the code compiles: PlatformIO prints [SUCCESS]. **Before uploading:** physically disconnect the pressure harness with USB off, retain the previously proven ToF connection, and confirm two local backup hashes. This build replaces the ToF-only app; be prepared to restore its saved original binary via STM32CubeProgrammer DFU if ToF regresses. Test using the already-verified ToF path only; do not enable pressure yet.

## Enabling hardware later — not yet approved

Only after verifying the v1.0.3 connector pins, switched rails, ToF breakout voltage and pressure ADC/transducer wiring, review/edit the tentative kPressureRail, kTofRail, TwoWire buses in src/main.cpp and opt into the following flags in platformio.ini:

    -D KEVIN_TOF_IO_ENABLED=1
    -D KEVIN_PRESSURE_IO_ENABLED=1
    -D KEVIN_CARRIER_V103_PORT_B_VERIFIED=1
    -D KEVIN_PRESSURE_INTERFACE_VERIFIED=1

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
