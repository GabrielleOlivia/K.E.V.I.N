# Physical integration checklist — 10 November 2026

Goal: demonstrate reliable acquisition, invalidation and recovery for real pressure, then identify and bring up one IMU. A successful day does not require all future modules to exist.

## Before connecting hardware

- [ ] Extract the package, create the Python environment and run the test suite.
- [ ] Start simulation; verify six cards, source labels, graphs and a sensor disable/restore cycle.
- [ ] Keep a copy of the known working pressure firmware and note its flashed revision.
- [ ] Record SensorHub/module PCB revisions and photograph readable IC markings for the team.
- [ ] Confirm the exact IMU: BHI360 vs another BMI/BHI model, and BMM350 presence/routing.
- [ ] Agree port ownership; close all other serial monitors before running the host.

## Pressure: preserve the verified setup

| Item | Preserve / verify |
|---|---|
| SensorHub | Custom ModularSim SAMD21; Feather M0 Express compiler variant |
| Module / sensor | Current SimModule Pressure board; fitted MPXV5010GP |
| Connection | Existing verified keyed Sensor A2 cable |
| MCU pads | SDA PA16; SCL PA17 |
| Variant indices | SDA 11; SCL 13 under the selected variant |
| Peripheral | SERCOM1, `PIO_SERCOM`, matching interrupt handler |
| ADC | MCP3426, address `0x68`, channel 1 |
| Acquisition | `0x88`, one-shot 16-bit, gain ×1; 100 kHz I2C |
| USB stream | 115200 setting; eight CSV fields plus `#` comments |

- [ ] Power off before changing sensor-module connections. USB disconnect testing is separate from hot-plugging an unverified sensor connector.
- [ ] Keep pressure at rest through startup; wait for `# READY`. An accepted stable baseline can still be wrong if pressure was applied during zeroing.
- [ ] Run `--mode physical --pressure-port PORT`; verify other modules remain missing.
- [ ] Compare the graph's delta with `raw - baseline`; values must remain ADC counts.
- [ ] Gently apply a known, controlled bench stimulus as in the existing test procedure. Confirm signed deviations and candidate counter behavior. Record conditions; do not call the count delivered breaths.
- [ ] Disconnect USB. Confirm immediate disconnected status when the OS reports loss, or timeout on silence, and a null current value.
- [ ] Reconnect to the same/stable port. Confirm new inferred session, startup/calibration handling, and recovery only with valid samples.
- [ ] Reset the board midstream. Confirm new header/session and cleared current reading; no mixing with prior candidate counts.
- [ ] Check a failed ADC/calibration row using the software fixture first. For physical fault injection, power down before changing module connections, then capture startup failure.
- [ ] Restore hardware; keep pressure at rest and send `z` using a serial terminal with the host stopped. Confirm calibration/read recovery. Record if opening the port resets this board.
- [ ] Archive the JSONL and original CSV for the test before log rotation overwrites them.

The existing firmware samples at roughly 6.7 Hz before overhead. Do not increase rate, change pins or introduce kPa conversion as part of first integration. Test changes separately against a pressure reference after identifying the actual analog path and supply.

## One IMU, then two

- [ ] Match the exact datasheet and board schematic; confirm supply/interface/pull-ups before wiring.
- [ ] Verify chip identity through the correct vendor initialization path.
- [ ] Begin with vendor-supported raw/fused data at a modest rate; capture initialization and read failures.
- [ ] Map the module output to the agreed quaternion convention, or register raw accelerometer/gyro channels separately if orientation is not yet available.
- [ ] Keep `calibration=unknown`/`valid=false` when initialization, firmware upload or fusion calibration is incomplete.
- [ ] Confirm axis directions with controlled rotations and document mounting.
- [ ] Add the physical head node via `--jsonl-port head_node=PORT`; keep chest simulated only for separate UI/integration testing, not physical neck-angle evidence.
- [ ] With two real IMUs, establish clock mappings and frame/mounting calibration before enabling derived geometry. Close reception timestamps alone are insufficient.

## Acceptance evidence to bring to the team

- [ ] Build/test output, firmware revision and registry used.
- [ ] Correct baseline and validity handling, not just changing numbers.
- [ ] Logged disconnect, invalid-data and reboot/recovery cases.
- [ ] Explicit list of physical vs simulated vs unavailable channels.
- [ ] Measured report rates, latency observations, and remaining hardware questions.

## CAN decision gate

Before coding an MCP2515 driver, agree controller oscillator, CAN bitrate, transceiver and logic voltage compatibility, SPI chip-select/interrupt pins, node-ID allocation, termination/topology, power/reference wiring, bus load, bus-off recovery and message priorities. The controller needs a CAN transceiver; a controller chip alone is not the physical bus interface. Bench-test a two-node bus before migrating pressure. The supplied fragmentation codec is only a testable proposal.
