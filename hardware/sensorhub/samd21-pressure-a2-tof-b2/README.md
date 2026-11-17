# SAMD21 SensorHub — pressure A2 + VL6180X ToF B2

> **Status:** bench firmware prepared from prior combined A2/B1 source. NOT YET COMPILED/UPLOADED/VERIFIED on physical SAMD21 in this branch. Pressure currently NACKs at 0x68 in both previous combined and older standalone firmware. These changes alone do not fix it.

## Hardware map (from MonitorHW(3).zip)
The EAGLE **samd21_sensorhub_1.2.5_dec2023.sch**, checked against the component placement in the companion PCB and the 2022 pinout drawing, establishes:
- **A2**: 4-pin pressure socket; SERCOM1 PA16 SDA, PA17 SCL, 3.3 V and GND. The A-side second socket shares this bus.
- **B2**: **5-pin** upper-right socket; SERCOM2 PA12 SDA, PA13 SCL, 3.3 V, GND, and additional **VSYS / nominal 5 V**. The lower B1 connector shares the same SERCOM2 bus in the reference design.
- On B2 schematic symbol `U$18`: **P1=VSYS, P2=GND, P3=3.3V, P4=SCL, P5=SDA**. These are *schematic pin designations, not a guarantee of physical order for the actual board revision*. The older 2022 pinout illustration shows its B2 contacts top-to-bottom SDA, SCL, 3.3 V, GND, VSYS when viewed as pictured. Verify the actual board silkscreen/revision and continuity before connecting.

**Do not force a 4-pin plug into the 5-position B2 socket or assume alignment.** Use a five-position keyed cable or verified 5-to-4 adapter wiring **GND, 3.3 V, SCL, SDA** to their exact ToF equivalents and **leave VSYS disconnected**. Do NOT route VSYS/5V to ToF, SDA, SCL or the SAMD21 3.3 V rail.

The pressure-board reference in MonitorHW `Pressure_Module_v2.1_jan2024.sch` uses MCP3426A0, 3.3 V supply, and a transducer symbol named `MP3V5050`. Actual pressure board photographed and discussed here is **not proven to have the same transducer or revision** (the visible silkscreen reads `MPXV70...`); identify its installed IC before specifying sensor supply or converting raw counts to pressure. MCP3426 communication at 3.3 V is datasheet-permitted.

## Firmware

This project copies the prior combined A2/B1 logic but **labels its SERCOM2 physical socket as B2**, adds `i` for I2C address scans on both buses, and keeps ToF model-ID checking and invalid-range handling. Moving the plug from B1 to B2 changes no SAMD21 I2C pins in the historical reference hardware, because both connect to SERCOM2.

- A2 pressure: MCP3426 at 0x68; one-shot CH1, 16 bit, gain 1, configuration 0x88; raw ADC counts only.
- B2 ToF: VL6180X at 0x29; model ID must be 0xB4 before standard sensor setup writes; raw mm at ~4Hz, valid only when `err=0`.
- No IMUs; particularly keep the BHI360 head IMU off bus B as it also uses 0x29.
- No simulated clinical pressure/air volume, no calibration of analog pressure.

## Staged validation — do not skip the physical connector check

1. **USB disconnected**, verify actual board revision and B2 socket contact mapping with the schematic and multimeter. Map ToF cable conductors end-to-end and confirm there is no VSYS short to 3.3V/GND or signal lines. Confirm supply voltage *at ToF breakout*, not only at B2 socket, **before** running.
2. Start with **ToF on B2 only**, pressure unplugged, both IMUs unplugged. Build/upload (commands below) and check `# TOF_MODEL_ID value=0xB4 ... identified=1`, `# TOF_READY B2` and valid `# tof` lines. Send `i`; expect 0x29 on bus B2, but no A2 pressure.
3. **USB disconnected**, remove ToF; connect **pressure on A2 only** with the original known-compatible 4-wire cable. Restart and send `i`: look for 0x68 on bus A2. We have previously observed NACK even with A2 PCB 3.3V and both lines idle at 3.3V; if it persists, do not conclude the two-sensor firmware is the problem. Investigate line continuity to the *ADC pads*, cable alignment/contact pressure, and actual ADC power/ground. A dedicated no-oscilloscope GPIO open-drain line reachability test may be needed.
4. Only when each test passes independently, power off and connect **both**. Observe 30+ seconds of simultaneous valid streams.
5. Capture source branch, firmware banner, COM port, board revision, wiring photos, sensor-level voltage, I2C scan output, invalid counts and fixed-distance results.

**Never hot-plug**, never continuity-test powered boards, never inject 5V onto data lines. This is a simulator research bench.

## Windows PowerShell

```powershell
cd "$env:USERPROFILE\Documents\K.E.V.I.N"
git fetch origin
git switch --track origin/feature/samd21-pressure-a2-tof-b2-diagnostic
cd .\hardware\sensorhub\samd21-pressure-a2-tof-b2
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run
# After successful build + verified B2 cable mapping, and with Serial Monitor closed:
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run -t upload --upload-port COM3
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" device monitor -p COM3 -b 115200 -f send_on_enter
```

If branch already checked out locally, `git switch feature/samd21-pressure-a2-tof-b2-diagnostic`. The earlier test firmware and branches are preserved.

### Monitor commands

- `s`: immediate ACK status on A2 0x68 and B2 0x29.
- `i`: address-only scan on both I2C buses (prints each acknowledged address). **This does not initialize unknown devices.**
- `p`: pause/resume sensor sampling.
- `h`: help.

Example `# STATUS pressure_A2_ack=1 tof_B2_ack=1 tof_initialized=1` is a **target**, not yet observed.

## Reference limitations and known failures

- A2 pressure hardware previously emitted raw ADC counts ~2500, but later 2026-11-17 returned address NACK `wire_status=2` on **both** a combined firmware and a local v0.3 standalone firmware, even with B1 unplugged and pressure PCB 3.3 V measured.
- A2-connected VL6180X independently ACKed and returned identity 0xB4 and raw distance samples 9–192 mm with `err=0`; nonzero errors (6,7,13) and raw 255 are invalid.
- The old firmware `feature/pressure-imu-integration` in the user's *local* worktree printed v0.3, but the GitHub branch head prints v0.4. This is local/remote version divergence, not proof of a defect.
- Old 2022 pinout graphic and later 2023 EAGLE schematic are references; exact live PCB revision and contact orientation still require physical verification.
- Combined B2 operation is **NOT YET demonstrated** by these source files.

See accompanying technical analysis report and Astra review prompt for the fault tree and controlled test plan.
