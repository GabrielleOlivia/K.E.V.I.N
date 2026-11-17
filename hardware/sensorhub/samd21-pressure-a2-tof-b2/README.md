# SensorHub bench diagnostic · pressure on A2 and ranging on B2

The pressure ADC stopped acknowledging even with the ToF removed. It used to give raw counts near 2500 on A2. The ToF previously returned model ID 0xB4 and valid ranges on **physical A2**. A2+B2 still requires a physical test. Use these instructions with the older ModularSim SAMD21 SensorHub and the two simulator modules.

## Match the connector before powering it

The archived `samd21_sensorhub_1.2.5_dec2023.brd` identifies itself as **v1.2.5, Dec 2023**. In the reference top/component view, USB is at the top. The table follows the solder pads from the top toward the bottom of that view. A loose plug viewed from its mating face can look reversed.

| Socket and reference | Pads from top to bottom | MCU and board trace |
| --- | --- | --- |
| A2, lower left, U$8, R90 | P1 GND · P2 3.3 V · P3 SCL · P4 SDA | SDA_SENSOR1 = PA16 (MCU pad 25, Feather index 11). SCL_SENSOR1 = PA17 (26, index 13). SERCOM1, pads 0 and 1, function C. A1 shares the pair. |
| B2, upper right, U$18, R270 | P5 SDA · P4 SCL · P3 3.3 V · P2 GND · **P1 VSYS / 5V net, leave empty** | SDA_SENSOR0 = PA12 (pad 21, index 28). SCL_SENSOR0 = PA13 (22, index 39). SERCOM2, pads 0 and 1, function C. B1 shares the pair. |

The Jan 2022 illustration also labels four contacts on B1. Its A-side `dig` column interchanges 11 and 13. Use the assembled PCB revision, Eagle pad nets and the actual Feather variant for those questions. The schematic's internal VERSION attribute still says V1.1 Jan 2022. Reference pull-ups on the hub are R1/R4 on A and R5/R6 on B, each 4.7 kΩ to 3.3 V.

1. Disconnect USB, backbone, debugger and all external supplies. Leave both IMUs and other peripherals off these buses throughout. Record the actual hub revision, USB orientation, connector counts and both sides of the modules. Identify the ToF breakout's designated power input and logic voltage rating. The bare VL6180X uses 2.6–3.0 V. Use B2 at 3.3 V only with a breakout documented for 3.3 V power and I/O.
2. With the five-position keyed B2 adapter detached, trace P2 to GND, P3 to the approved supply input, P4 to SCL and P5 to SDA. The P1 cavity must have no conductor to the module. Check each wire and isolation between wires. Check A2 separately. On the unpowered assembled circuit identify named ground, 3.3 V and signal test points. Pull-ups and capacitors can produce finite/changing resistance on a PCB. A direct short is a stop.
3. Fit the verified adapter to the hub with its module end **empty**. With probes/clips positioned safely, power the hub alone and check each far-end voltage relative to known ground. The breakout supply and released SDA/SCL should be around 3.3 V in this design. Power down again before connecting a sensor. Stop on an ambiguous mapping, an incompatible breakout, overvoltage or a missing ground. Never hot-plug, apply 5 V, or take resistance readings with power present.

The Jan 2024 pressure schematic shows IC2 MCP3426A0-E/MC with CH1+ on A0_PRESSURE and CH1− at ground. At the reference DFN, pad 3 is VDD, 6 VSS, 4 SDA, 5 SCL. R28/R29 are 4.7 kΩ pull-ups to 3.3 V. U$3 is a symbol named MP3V5050, also fed 3.3 V. A partial MPXV70… board legend is insufficient to identify the installed transducer. Record its full **IC** marking, ADC marking, package and PCB revision before determining the module's analog supply or transfer function. The ADC alone supports 2.7–5.5 V. Keep the digital bench setup at verified 3.3 V.

## Build and upload from Windows PowerShell

Use an independent worktree to preserve a local v0.3 checkout or uncommitted files. Start in the existing repository. The worktree destination must be new on first use. On later visits enter the existing review worktree and check its HEAD.

```powershell
Set-Location "$env:USERPROFILE\Documents\K.E.V.I.N"
git fetch origin
if ($LASTEXITCODE -ne 0) { throw "Fetch failed" }
$branch = "review/samd21-a2-b2-bench"
$review = Join-Path (Split-Path (Get-Location) -Parent) "KEVIN-a2-b2-review"
git worktree add --detach "$review" "origin/$branch"
if ($LASTEXITCODE -ne 0) { throw "Use a new destination or open the existing review worktree" }
Set-Location $review
git log -1 --oneline --decorate
git status --short
if ((git rev-parse HEAD) -ne (git rev-parse "origin/$branch")) { throw "Wrong revision" }
if (git status --porcelain) { throw "Review worktree has changes" }
Set-Location .\hardware\sensorhub\samd21-pressure-a2-tof-b2
$pio = "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe"
$normal = "adafruit_feather_m0_express"
& $pio run -e $normal -e a2_reachability
if ($LASTEXITCODE -ne 0) { throw "Build failed" }
& $pio device list
```

Connect only the verified hub to USB for the first upload. Confirm COM3 belongs to it by disappearance/reappearance with no sensors being moved. Close any monitor first. Verify the commit against the review supplied with this branch. Two PlatformIO SUCCESS entries establish build success.

```powershell
function Flash-Bench([string]$FirmwareEnv) {
    & $pio run -e $FirmwareEnv -t upload --upload-port COM3
    if ($LASTEXITCODE -ne 0) { throw "Upload failed" }
}
function Monitor-Bench {
    & $pio device monitor -p COM3 -b 115200 -f send_on_enter -f log2file
}
Flash-Bench $normal
```

For each stage below, unplug USB and all other power, connect only the listed modules, reconnect USB, then run `Monitor-Bench`. Use Ctrl+C to close the monitor. The log2file filter prints the log path (under `logs/` in PlatformIO Core 6.2). If the port changes, identify the runtime port with `& $pio device list` and substitute it. If you miss the banner, send `h` followed by Enter. The normal image replies `# KEVIN SAMD21 A2+B2 review v1`. Each command is one character followed by Enter.

## Staged bench matrix

Selecting `b`, `a` or `c` starts only the selected buses and reports ACK. `s` repeats the targeted check. `i` scans the selected buses, address-only, 0x08–0x77. `off` / wire code −1 means the bus was skipped. Leave acquisition off if an unexpected device appears. Once the intended hardware is identified, `g` enables acquisition and register writes. The ADC has no unique ID register. A ToF register **read** first sends its two-byte index, so a foreign device must be removed even before `g`.

| Stage | Commands | PASS pattern (expected) | FAIL or STOP |
| --- | --- | --- | --- |
| 1. ToF on B2 alone | `b`, `i`, `g`, `s` | `bus=B2 address=0x29`; `# TOF_MODEL_ID value=0xB4 expected=0xB4 identified=1`; `# TOF_READY B2 live ranging`; repeated `,err=0,valid=1` and a plausible change when a matte white card is moved from about 30 to 60 mm. A2 shows `off`. | `tof_B2_ack=0` or repeated read failure = B2 link/enable/adapter diagnosis. `STOP TOF_WRONG_DEVICE` = power down and identify the responder. An occasional `raw_mm=255,err=7,valid=0` is a discarded frame. |
| 2. Pressure on A2 alone | `a`, `i`, `g`, `s` | `bus=A2 address=0x68`; `# PRESSURE_PRESENT A2 0x68`; repeated `# pressure,t_ms=…,raw_adc=…,valid=1,pressure_calibrated=0`. B2 shows `off`. There is no expected count at rest. | `pressure_A2_ack=0`, often `pressure_wire=2` = address-phase failure. Skip acquisition if there is no intended responder. ACK with `short_read`, `config_mismatch` or `adc_busy_timeout` = acquisition failure. Keep the modules separate. |
| 3. Both, only after each passes | `c`, `i`, `g`, `s` | `# STATUS pressure_A2_ack=1 tof_B2_ack=1 tof_initialized=1 pressure_wire=0 tof_wire=0`. Log at least 30 s of interleaved fresh samples, sensor timestamps advancing on both streams; move only the optical target. | FAIL on address loss, a stalled stream, repeated transport faults, or no valid samples from either device. Count optical invalid frames separately. Power off, return to the last passing single-sensor setup and recheck local supplies under combined load. |

STOP on `PINMAP_MISMATCH`, `PINMUX_MISMATCH`, `idle_line_low`, a hung monitor after a bus command, rail collapse, heating or any unsafe physical check. Disconnect power and inspect. The polling deadlines surround Wire calls. This SAMD core can itself block inside a transaction.

## No-scope isolation for a pressure NACK

Start with all power removed. Trace A2 P4 and P3 to independent, identified SDA/SCL endpoints on the pressure board. Measure the cable independently end-to-end and for crosses while gently flexing it. On the matching reference board use the **signal** sides of R28/R29. Trace from each pad toward the ADC if accessible. For rail checks use a verified local bypass capacitor across VDD/VSS. Attach probes unpowered. Avoid probing adjacent live DFN pads.

If the net mapping, passive pull-ups and rail isolation pass, but you still need to see which physical line the MCU can reach, use the separate GPIO image. Remove every other peripheral/controller and external supply. A line shorted directly to 3.3 V also reads HIGH at idle; resolve suspicious low resistance or unidentified active circuitry before applying a pulse. Use a verified 3.3 V pressure module, or start with an empty verified cable. It is safe to stop at the passive checks where no accessible measurement point exists.

1. Close the monitor. With the hub alone, run `Flash-Bench a2_reachability`. Disconnect power, attach the verified pressure setup and DMM clips, reconnect USB, open `Monitor-Bench`, send `h`. Expect `# GPIO A2 ONLY v1`. Both released signal pads should read approximately 3.3 V relative to module ground.
2. Send `d` to sink only PA16/SDA for 3 s. Expect module SDA near 0 V and SCL near 3.3 V, followed by both high. Send `k` for PA17/SCL. Expect SDA high and SCL near 0 V, followed by both high. With one meter, repeat commands for each endpoint. Power off to reposition clips where a slip could bridge pads. The image never transmits I²C or drives a HIGH; a pulse requires a new command after release.
3. PASS is four matching meter observations plus release on both lines. The `# GPIO RELEASED` message describes the MCU end only. Opposite line low = crossed wiring. Host pad low and remote pad high = open path between them. Both low or failed release = STOP, power down and inspect. A slow pulse cannot validate bit timing, rise time, the return ACK, or the ADC's silicon.
4. Restore the normal image with the hub alone using `Flash-Bench $normal`. Power off before reconnecting a module.

As a control, place the formerly working ToF on **physical A2** with its original verified four-wire lead and approved supply. In the normal image use **`a`, then `i` only**. An A2-only 0x29 ACK demonstrates present-day digital reachability for that cable/module. To repeat the full identity/range control use the historical A-side ToF image at `0f58395` in `hardware/sensorhub/samd21-vl6180x-a1`. After any control, restore the review image and power down before reconnecting. If an identified, properly powered ADC still fails at its factory address on two known-working 3.3 V hosts, while a matching good module works with the same leads, suspect the pressure assembly. A solder/trace defect can mimic damaged silicon.

## Firmware and evidence

The reviewed inputs were B2 `becb92f`, B1 `3f2e8e7`, A-side ToF `0f58395` and pressure/IMU `03a6552`. Published `68c70d0` contains a v0.3 pressure banner; the supplied local flash has no verified SHA. The v0.4 integration latches pressure presence at boot and is not the B2 ranging program. A Wire code of 2 is an address-phase failure and can include a bus-state rejection.

The normal image uses separate TwoWire objects, function-C pinmux after begin(), matching SERCOM1/2 handlers and 100 kHz. A pressure one-shot writes 0x88, polls the same conversion after 110 ms with a 200 ms busy cutoff, checks the three returned bytes and expects ready config 0x08. It emits signed counts at a nominal 4 Hz. ToF uses default 7-bit 0x29 and checks register 0x0000 before initialization. It checks the interrupt-clear write before publishing a frame and discards nonzero error codes and the 0xFF sentinel. Each ToF wait can take 100 ms plus Wire time. Both buses share CPU time, ground and power. Save the bench log and record valid/invalid totals per sensor alongside firmware SHA, adapter orientation, module revisions and local rail measurements.

[Microchip MCP3426/7/8 data sheet, §§ 4–5](https://ww1.microchip.com/downloads/aemDocuments/documents/OTH/ProductDocuments/DataSheets/22226a.pdf) · [Microchip SAM D21 multiplexed signals](https://onlinedocs.microchip.com/oxy/GUID-22527069-B4D6-49B9-BACC-3AF1C52EB48C-en-US-21/GUID-DEBE7851-16DD-4D3B-8C60-F2627E3B3DEE.html) · [ST VL6180X data sheet](https://www.st.com/resource/en/datasheet/vl6180x.pdf) · [ST AN4545](https://www.st.com/resource/en/application_note/an4545-vl6180x-basic-ranging-application-note-stmicroelectronics.pdf) · [Adafruit variant at release 1.7.16](https://github.com/adafruit/ArduinoCore-samd/blob/1.7.16/variants/feather_m0_express/variant.cpp) · [NXP I²C specification](https://www.nxp.com/docs/en/user-guide/UM10204.pdf).

## Live bench: A2 pressure-only scan — 2026-11-17

User reported output from the **reviewed normal firmware** on SAMD21 COM3 after selecting A2 with pressure on A2 and B2 disabled:

```text
# STATUS pressure_A2_ack=0 tof_B2_ack=off tof_initialized=0 pressure_wire=2 tof_wire=-1
# SCAN_START bus=A2
# SCAN_END bus=A2 count=0
# STATUS pressure_A2_ack=0 tof_B2_ack=off tof_initialized=0 pressure_wire=2 tof_wire=-1
```

**Observed:** A2 command path executed, but no device ACKed; `wire_status=2` is an address-phase failure. B2 being `off` is intentional, not evidence B2 failed. This is consistent with the prior v0.3 and combined-firmware pressure failures. DC 3.3 V on module VCC/SDA/SCL does not establish dynamic signal reachability.

**Next discriminating control (safer than driving test pins first):** unpower everything, remove pressure A2, use the *previously working ToF with its verified four-wire connection on physical A2*, leave B2 empty, power USB, start monitor, send `a`, then `i`. Expect `# SCAN_FOUND bus=A2 address=0x29` if A2 bus and that cable are presently functional. **Do not send `g` while a ToF is plugged into A2 in the pressure-oriented review firmware**, because `g` is designed for MCP3426 acquisition on A2. Restoring pressure requires power off. If the 0x29 control passes, narrow pressure diagnosis to its cable/connector/ADC-side routing rather than declaring the SERCOM1 interface broken. If it fails, use the optional passive and low-only reachability diagnostics under the documented preconditions.
