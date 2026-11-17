# K.E.V.I.N. — STM32F405 Pressure-Only Port A Lower Diagnostic

**Status: code prepared but not compiled or flashed on physical hardware. Hardware pin ordering and supply validation outstanding.**

## Why this branch exists

User discovered that their pressure board responded on the older setup with the original four-wire keyed cable, while individual jumper wires caused intermittent/no communication. The goal is to isolate **only the MCP3426 pressure ADC** on the **four-pin Port A lower** connector of the STM32 SensorHub v1.0.3, with the ToF unplugged. This diagnostic lives on its own branch so earlier working ToF firmware remains untouched.

### Proposed STM32 pinout (from newer v1.1.0b KiCad, NOT confirmed for user's v1.0.3)

| Signal | Port A lower on newer reference PCB | STM32 |
| --- | --- | --- |
| Ground | P1, GND | GND |
| Switched rail | P2, 3.3V_OUT3 | Controlled by PC13 |
| I²C clock | P3, SCL1 | PB6 |
| I²C data | P4, SDA1 | PB7 |

MCP3426 uses I²C 7-bit address **0x68**, 100kHz. Software uses `TwoWire tofBus(PB7, PB6)` as a reused bus object, but does **not** initialize or power the ToF (flag 0, PC9 untouched). No Port B GPIO / I²C2 is driven. The only switched rail used *after explicitly enabling pressure* is PC13 for Port A lower.

## Important voltage limitation — pressure response cannot be validated on this 3.3V connector alone

The physical Jan 2026 pressure module uses **MPXV5010GP**, which requires **4.75–5.25V supply** (NXP MPX5010/MPXV5010 datasheet). The adjacent STM32 Port A lower provides only **3.3V in the v1.1.0b reference**. A keyed connector physically fitting does not prove matching order or voltages. MCP3426 might acknowledge at 3.3V, but the transducer won't be within its rated operating supply range. The presence of arbitrary ADC counts must NOT be interpreted as working pressure sensing.

**Do not power or upload an active sensor build until the actual v1.0.3 pin order, cable pin order, and safe logic voltage levels have been confirmed. Do not feed 5V into lower Port A's 3.3V pin or STM32 SDA/SCL.** A proper full-pressure test will require a verified 5V supply path or adapter with correct ground and 3.3V-compatible I²C logic; the adapter is not provided by this firmware.

## Build safe/locked firmware

The `platformio.ini` defaults are **pressure OFF**, ToF OFF:

```ini
-D KEVIN_TOF_IO_ENABLED=0
-D KEVIN_PRESSURE_IO_ENABLED=0
-D KEVIN_PRESSURE_A_LOWER_PINOUT_VERIFIED=0
```

This compiles a USB-serial safety heartbeat, but no sensor GPIO or I²C activation. Build:

```powershell
cd "$env:USERPROFILE\Documents\K.E.V.I.N"
git fetch origin
git switch --track origin/feature/stm32f405-pressure-only-porta-lower
cd .\hardware\sensorhub\stm32f405-pressure-tof
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run
```

If the local branch already exists, use `git switch feature/stm32f405-pressure-only-porta-lower` and `git pull --ff-only`.

After actual lower Port A connector, power and logic verification (NOT mere connector fit), change `KEVIN_PRESSURE_IO_ENABLED` and `KEVIN_PRESSURE_A_LOWER_PINOUT_VERIFIED` to **1**, leave `KEVIN_TOF_IO_ENABLED=0`, and rebuild. Only do this when the ADC/module supply connections are electrically safe, and do not claim calibrated transducer pressure without its separate verified 5V.

If and only if safe, flash through STM32CubeProgrammer USB DFU with original 1MB STM32 backup retained, program `.pio/build/micromod_f405_pressure_tof/firmware.bin` at `0x08000000` with Verify, no full chip erase or option-byte changes. Restart without BOOT. Check COM port and use 115200 Serial Monitor.

Expected **I²C diagnostic** output (not yet observed):

```text
# KEVIN STM32 PRESSURE ADC ONLY lower Port A v0.1
# ToF disabled/disconnected; only MCP3426 address 0x68 on I2C1
# PRESSURE_ADC_PRESENT (I2C/ADC diagnostic only)
# STATUS pressure_ack=1 tof_ack=DISABLED
# pressure_adc,t_ms=...,raw_adc=...,adc_conversion_valid=1,pressure_calibrated=0
```

Send `s` to repeat address ACK check. `z` deliberately prints `# CALIBRATION_DISABLED`, because this firmware deliberately does not claim correct pressure transducer voltage or calibration. With pressure disabled, instead expect `# SAFETY_LOCK_HEARTBEAT`.

If you get `ack=0`, **do not repeatedly swap powered connections**. Verify voltage rails, orientation, pin order and cable continuity with the team or multimeter. Successful 0x68 ACK only means the ADC answered; the sensor transducer needs its rated 5V before testing actual pressure response.

## Evidence

- Previously: ToF on Port A upper confirmed working on STM32.
- Previously: MCP3426 on Port B intermittently returned raw ADC 2503–2508 with ToF simultaneously, then disappeared.
- Previously: pressure on shared I2C1 caused both sensors' ACKs to disappear; ToF recovered with pressure disconnected.
- Pressure on Port A lower with dedicated pressure-only STM32 firmware: **NOT YET TESTED**.

## Known-good firmware preservation

Original STM32 full 1MB flash backups were made and SHA256 compared previously. Previous working ToF mode is in `feature/stm32f405-pressure-tof-integration`. This pressure-only branch is an isolated experiment, not a release for real patient equipment.
