# K.E.V.I.N. — STM32F405RG MicroMod SensorHub migration (USB-only starter)

**Status: prepared in GitHub, not yet built, flashed, or tested on the user's STM32.** The SAMD21 pressure + dual IMU code is preserved untouched in `hardware/sensorhub/pressure-imu`. This separate project is for identifying a candidate new controller and validating its programming/USB communication *after* a firmware-backup decision.

## Evidence from teammate's GitHub

The teammate's repository `OlympusSixtems/KEVIN` has a dedicated `feature/stm32f405-vl6180x-tof-probe` branch. Unlike its root PlatformIO project (which remains **SAMD21**), the project in `firmware/tof_probe_f405` targets:

- **Processor:** SparkFun MicroMod STM32, STM32F405RG, on RobotPatient *SensorHub MicroMod Carrier v1.1.0b*.
- **PlatformIO:** `platform = ststm32`, `board = sparkfun_micromod_f405`, `framework = arduino`; USB CDC flag `PIO_FRAMEWORK_ARDUINO_ENABLE_CDC`.
- **Upload configuration in teammate's ToF project:** `upload_protocol = dfu`, requiring deliberate entry to STM32 ROM DFU bootloader. Do NOT blindly set this on a board holding irreplaceable existing firmware.
- **VL6180X ToF:** diagnostics only (raw mm, not validated CPR compression depth). Teammate's 2026-10-13 report documents a successful **build** but says **not flashed / not hardware-tested**.

Sources:
- https://github.com/OlympusSixtems/KEVIN/tree/feature/stm32f405-vl6180x-tof-probe/firmware/tof_probe_f405
- https://github.com/OlympusSixtems/KEVIN/blob/feature/stm32f405-vl6180x-tof-probe/docs/reports/sensorhub_stm32f405_vl6180x_implementation.md
- https://github.com/OlympusSixtems/KEVIN/blob/feature/stm32f405-vl6180x-tof-probe/docs/reports/sensorhub_stm32f405_vl6180x_assessment.md

**Critical:** The teammate's documentation is evidence about *their tested/designed carrier*, not proof that the user's currently connected STM32 is the same model/revision. Verify the silkscreen and USB device IDs.

## Carrier signals from teammate's design review (MUST verify physical board)

| Connector | I2C pins on STM32 | Sensor power-switch GPIO (HIGH = on) |
|---|---|---|
| Port A upper, near USB-C (U$8) | I2C1, SDA PB7, SCL PB6 | PC9 / G4 / 3.3V_OUT2 |
| Port A lower, near RST (U$55) | **same I2C1** SDA PB7, SCL PB6 | PC13 / G5 / 3.3V_OUT3 |
| Port B, near BOOT (U$59) | I2C2, SDA PB11, SCL PB10 | PC8 / G3 / 3.3V_OUT1 |

Power is switched by hardware rail circuits; this USB-only starter intentionally does NOT change PC8, PC9, PC13 or any sensor rail.

**I2C address collision:** Both BHI360 IMUs have reported `0x29` in prior SAMD21 tests, and VL6180X normally uses `0x29`. There are only two documented carrier I2C buses. If you need all three `0x29` devices simultaneously, plan an **I2C multiplexer, separate additional bus, or controlled address-reassignment strategy**; do not plug two live devices with the same address into the same bus and expect to identify them independently. The two Port A connectors have separately switched 3.3 V rails but **share I2C1**, so they are NOT independent buses. Before using any ToF port, verify its breakout is electrically compatible with the offered power rail: the bare VL6180X IC is not specified for direct 3.3 V operation.

## Suggested eventual K.E.V.I.N. allocation (design idea only)

- **Port A upper:** CHEST BHI360 `0x29`, enable with PC9 only when safely connected.
- **Port A lower:** pressure MCP3426 `0x68`, enable with PC13 only when attached; it shares bus I2C1 with CHEST.
- **Port B:** HEAD BHI360 `0x29`, enable with PC8 only when safely connected.
- **ToF sensor:** requires its own address-domain solution (e.g. suitable I2C mux or independent bus) if the other two IMUs keep address `0x29`. Do not assign it to Port B alongside the HEAD on an unchanged `0x29` bus.

Before connecting anything, check actual connector pinouts, rail voltages and current draw against hardware design. The existing fragile individual female-to-female jumper wires need secure, correctly keyed connections and strain relief. Power OFF before any change.

## Windows first steps — NO flash or firmware change

1. In **Device Manager**, record the device's exact entry under Ports / USB and Hardware IDs (VID/PID), and photograph the STM32 processor and carrier revision silkscreen. A board being detected as USB does **not** mean we know its bootloader or current firmware.
2. If USB application currently exposes a COM port, obtain its current serial output *read-only* if the team agrees. Document any banner/version. **Do not assume COM3**: that was the SAMD21.
3. Check whether the current STM32 application firmware is backed up and whether its source exists. The teammate's documented STM32 had `VID_2FE3&PID_0004`, a `CDC ACM serial backend` and COM8, suggesting a possible Zephyr image (inference only). Their assessment says source and backup were unknown. Do not erase valuable Zephyr firmware.
4. After verifying the physical board matches `sparkfun_micromod_f405`, build this starter **offline**:

   ```powershell
   git fetch origin
   git switch --track origin/feature/stm32f405-sensorhub-bringup
   cd ..\stm32f405-bringup
   & "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run
   ```

   The `cd` assumes the shell starts in `hardware\sensorhub\pressure-imu`. If already tracking the branch, use `git pull --ff-only` instead of `git switch --track`.

5. **Do not run `run -t upload` yet.** Flashing this tiny USB-only app would still overwrite the STM32's existing application. A successful build is only proof the computer has the toolchain and the source compiles.

After firmware provenance/backup and team approval are resolved, decide which programming method is appropriate (ST-LINK/SWD vs ROM DFU) and validate the USB heartbeat on the specific physical MCU. Only then add read-only BHI360 probes, and much later firmware upload with stable wiring and image verification.

## STM32–SAMD21 difference that matters

The SAMD21 prototype used Arduino pin indices 11/13 and 28/39 with `SERCOM1_Handler` / `SERCOM2_Handler`. **None of those MCU pin mappings or interrupt handlers transfer directly.** The high-level code (pressure event state machine, CSV format, serial command protocol, Bosch BHI360 device API) can be reused, but the bus construction, power rail control, timing and platform drivers must be ported and hardware-tested.

For infant manikin research and simulation only, not clinical monitoring.
