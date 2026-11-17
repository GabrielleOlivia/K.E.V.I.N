# Pressure-only bench test on the known-working STM32 Port A upper

**This is a temporary pressure diagnostic. It is not the final four-sensor firmware.**

## Motivation

The ToF has already demonstrated real `err=0,valid=1` readings on the physical v1.0.3 STM32 carrier via **Port A upper**, using PC9 for switched power and I2C1 PB7/PB6.

The four-contact **SimModule Pressure v2.0.0, Jan 2026** is physically marked **MPXV5010GP**. The earlier SAMD21 bench project reports an onboard MCP3426 ADC at 7-bit address **0x68**, writing **0x88** and reading three data/config bytes. Its I2C port was previously tested on the SAMD21 but has not yet been tested on STM32.

Rather than experiment with the unverified five-pin Port B on the v1.0.3 carrier, this temporary program reuses the known-working four-pin Port A upper connection for the pressure sensor, **one sensor at a time**. No Port B, I2C2 or PC8 pin is configured.

## Safety correction after first successful compile (2026-11-17)

The user successfully built the pressure-only diagnostic on the STM32F405 (RAM 5,208 bytes; flash 34,052 bytes). **This is compile-only evidence; no pressure communication has been observed.**

The physically confirmed pressure IC **MPXV5010GP** requires **4.75–5.25 V** supply under its datasheet. The known-good ToF connector, Port A upper, uses a **switched 3.3 V rail** in the available v1.1.0b reference and physically powered the ToF on v1.0.3. Supplying a bare MPXV5010GP from 3.3 V would be out of specification; an I2C ACK alone would not prove valid pressure sensing. The actual pressure module's **separate 5 V transducer supply**, ADC voltage, I2C voltage levels and connector pinout remain unverified.

**Safety fix now applied:** `platformio.ini` defaults to `KEVIN_PRESSURE_PORTA_ELECTRICAL_VERIFIED=0` and firmware prints a safety-lock heartbeat without energizing Port A or probing I2C. Only change this flag to 1 after confirming the correct pressure PCB power arrangement and signal/pin mapping; merely toggling it will NOT magically provide 5 V on the Port A connector. Therefore do NOT upload this branch for a pressure hardware test yet. Use known-good SAMD21 Sensor A2 wiring for a separately verified pressure test, or obtain the matching v1.0.3/v2.0 PCB schematic and a multimeter/power-supply check.

Relevant datasheet: https://www.nxp.com/part/MPXV5010GP

## Critical safety precondition

With **USB power OFF**, disconnect the ToF module from Port A upper and disconnect **all** pressure jumper wires from Port B. Do not leave loose wires attached while powering the board.

Use ONLY a **matching four-pin keyed cable** whose pin ordering and voltage requirements are confirmed compatible with the pressure PCB and SensorHub Port A upper. A physically fitting plug or matching wire colors alone is insufficient proof. The photographed pressure module has four electrical pads; the unverified Port B has five contacts including 5V. Do not plug a four-contact module into the five-pin Port B using arbitrary wire colors.

If the pressure PCB is wired differently from the ToF PCB, or 3.3V is not an acceptable module supply, **STOP and DO NOT FLASH/RUN THIS TEST**. Consult the correct PCB schematic or electrically check before powering it. This program only switches on PC9 (known from ToF), not 5V. The MPXV5010GP sensor itself typically requires a 5V supply, so even if the MCP3426 powers up, observed ADC counts may not correspond to calibrated pressures. Check the module's onboard supply/conditioning separately.

## Build

In PowerShell from the local repo (do not lose uncommitted changes):

```powershell
cd "$env:USERPROFILE\Documents\K.E.V.I.N"
git fetch origin
git switch --track origin/feature/stm32f405-pressure-porta-probe
cd .\hardware\sensorhub\stm32f405-pressure-porta-probe
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run
```

Stop here if the firmware does not build. This project is a separate temporary branch so the validated ToF application and combined ToF+pressure source remain preserved.

## After matching electrical pinout is confirmed, upload deliberately

Use STM32CubeProgrammer USB DFU. First preserve the original 1MB backup in two identical verified files (previously done; restore not tested). Enter DFU BOOT+RESET, use `.pio/build/micromod_f405_pressure_porta/firmware.bin` and address `0x08000000`; verify after programming, reset without BOOT.

## Expected serial output

These are **examples only**; not actual hardware results:

```text
# KEVIN STM32 PRESSURE-ONLY Port A upper v0.1
# Port B disabled; ToF intentionally disconnected
# ADC_PROBE bus=I2C1 port=A_upper address=0x68 ack=1
# pressure,t_ms=1000,raw_adc=2542,valid=1,total_valid=1,total_invalid=0
```

If `ack=0`, communication is not established. Do not reconnect wires while powered. If `ack=1` but samples fail, inspect `# ADC_FAULT` lines and do not treat failed data as zeros.

First test raw resting counts with no pressure applied, then gentle syringe pressure and release while watching for changing counts. Readings are **not** calibrated to Pa/kPa, flow or tidal volume.

After pressure-only communication works, plan **simultaneous** ToF+pressure on v1.0.3. One possible design puts both devices on the shared Port A I2C1 bus (0x29 and 0x68 do not conflict), provided the Port A lower connector pinout and switched power rail are verified. This step is NOT proven yet. Future BHI360 devices introduce additional 0x29 conflicts and require address management.
