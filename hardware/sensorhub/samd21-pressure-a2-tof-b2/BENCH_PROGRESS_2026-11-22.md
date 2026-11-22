# K.E.V.I.N. SensorHub — A2 pressure + B1 ToF bench progress (22 November 2026)

**Status: simultaneous I²C discovery and interleaved raw data acquisition demonstrated on the physical bench. Reliability and calibration remain OPEN.**

This is a **measured progress record**, not a medical-device validation, and the results are limited to an infant patient-monitor **training simulator**. It documents the user's Serial Monitor output and physical observations on 22 November 2026. Do not substitute the illustrative patterns in older READMEs for the measurements below.

## Physical setup and code provenance

| Item | Physical connection / configuration |
| --- | --- |
| Controller | ModularSim SAMD21 SensorHub, Feather M0 Express PlatformIO variant; actual PCB revision should be confirmed from the unit |
| Pressure module | MCP3426-based analog pressure module, connected to physical **Sensor A2** |
| Pressure I²C | SAMD21 **SERCOM1**, PA16 SDA (variant index 11), PA17 SCL (index 13); target 7-bit address `0x68` |
| Distance sensor | ST VL6180X ToF breakout, connected to physical **Sensor B1** |
| ToF I²C | SAMD21 **SERCOM2**, PA12 SDA (variant index 28), PA13 SCL (index 39); target 7-bit address `0x29` |
| Power/wiring | Existing four-wire connections. Their exact physical contact order and voltage compatibility must be checked against the assembled board before modifying cables |
| Interface | Windows COM3, USB serial 115200 baud, PlatformIO `send_on_enter` and `log2file` |
| Firmware used during test | Reviewed diagnostic `review/samd21-a2-b2-bench/hardware/sensorhub/samd21-pressure-a2-tof-b2`, banner `# KEVIN SAMD21 A2+B2 review v1` |
| Firmware in this branch | **Unmodified copy of the reviewed diagnostic** inherited from that branch; code exists in `src/main.cpp`, `src/a2_reachability.cpp`, `include/` and `platformio.ini` |

**Important physical/logging distinction:** The firmware's `B2` strings are **logical labels** for the Sensor B (SERCOM2) bus. In the 2023 reference schematic, **B1 and B2 share SERCOM2**. The ToF was **physically plugged into B1**, NOT B2, for these reported tests. No firmware changes or new uploads were reported during this session, so this branch intentionally preserves the tested source instead of changing print labels and then claiming that modified image was tested.

Reference review commit/branch used to derive this branch: `review/samd21-a2-b2-bench` at `d58f481205af6a81543e5e65b624cb18f2f20a74` when this record was created. The binary flashed to the physical board was not independently hashed. Its banner and runtime behavior match the reviewed source.

## What was actually tested

1. **ToF only, physical B1:** With stage `b` and address scan `i`, the bus returned `0x29`. `g` identified VL6180X model ID `0xB4` and enabled live ranging. Moving the user's hand yielded valid distances **27–180 mm** in the supplied first B1-only stream, along with some invalid `err=7` / `err=13` frames.
2. **Both I²C buses selected, first attempt:** `c`, `i`, `s` found pressure `0x68` on A2, but **no ToF address** on B1/SERCOM2 (wire status `2`: address NACK).
3. **Both buses after reseating wires:** The user pushed the connections more firmly in place. Repeating the test found **both addresses**: A2 `0x68`; B1/SERCOM2 `0x29`, with both `wire_status=0`.
4. **Simultaneous measurements:** After `g`, the firmware reported `# PRESSURE_PRESENT A2 0x68`, ToF model `0xB4`, and `# TOF_READY B2 live ranging`. Pressure and ToF rows alternated over time. Pressure raw ADC initially stayed about **2493–2499 counts**, and valid moving-hand ToF measurements were about **36–190 mm**. These are raw readings, not calibrated pressure or an anatomical measurement.
5. **Later hand-hold and blowing test:** In the additional 22 Nov log, the user's hand was held over/near the ToF and the user reported blowing on the pressure sensor. While the hand was relatively still, many consecutive ToF readings had `err=0,valid=1`, often near **28–36 mm**. Pressure raw ADC readings began near **2498–2502**, then changed substantially; an observed maximum was **6541**. **The exact moment and route of airflow were not separately timestamped**, so the spikes are *consistent with* the reported blowing but are not a controlled pressure-vs-time calibration.

### Evidence excerpts from the actual serial output

```text
# STATUS pressure_A2_ack=1 tof_B2_ack=1 tof_initialized=0 pressure_wire=0 tof_wire=0
# SCAN_START bus=A2
# SCAN_FOUND bus=A2 address=0x68
# SCAN_END bus=A2 count=1
# SCAN_START bus=B2
# SCAN_FOUND bus=B2 address=0x29
# SCAN_END bus=B2 count=1
# PRESSURE_PRESENT A2 0x68
# TOF_MODEL_ID value=0xB4 expected=0xB4 identified=1
# TOF_READY B2 live ranging
```

Interleaved raw frames, recorded with both devices connected:

```text
# pressure,t_ms=70181,raw_adc=2496,valid=1,pressure_calibrated=0
# tof,t_ms=70330,raw_mm=120,err=0,valid=1
# pressure,t_ms=70433,raw_adc=2495,valid=1,pressure_calibrated=0
# tof,t_ms=70583,raw_mm=158,err=0,valid=1
```

Hand held near ToF, alongside near-baseline pressure values (second log):

```text
# pressure,t_ms=39007,raw_adc=2500,valid=1,pressure_calibrated=0
# tof,t_ms=39155,raw_mm=32,err=0,valid=1
# pressure,t_ms=39257,raw_adc=2501,valid=1,pressure_calibrated=0
# tof,t_ms=39406,raw_mm=33,err=0,valid=1
```

Pressure response from that second log:

```text
# pressure,t_ms=55463,raw_adc=2507,valid=1,pressure_calibrated=0
# pressure,t_ms=55717,raw_adc=2522,valid=1,pressure_calibrated=0
# pressure,t_ms=55969,raw_adc=6541,valid=1,pressure_calibrated=0
# pressure,t_ms=56220,raw_adc=5575,valid=1,pressure_calibrated=0
# pressure,t_ms=56472,raw_adc=5624,valid=1,pressure_calibrated=0
# pressure,t_ms=56723,raw_adc=2556,valid=1,pressure_calibrated=0
```

### Unresolved pressure transport faults — NOT a complete reliability PASS

The later session included **two** pressure I²C failures (around 49.5 s and 58.9 s since startup), both followed by automatic recovery:

```text
# PRESSURE_SAMPLE_INVALID reason=short_read rx_count=0
# PRESSURE_FAULT reason=address_phase wire_status=2
...
# PRESSURE_RECONNECTED A2 0x68
```

The ToF continued to emit frames during these episodes. This demonstrates **partial fault isolation**, not an uninterruptible pressure data stream. Address ACK=1 shows a responder at `0x68`, not guaranteed uninterrupted ADC communication. The earlier recovery after seating the wires makes cable/contact intermittency plausible, but it **does not prove the root cause**. Supply integrity, connector continuity, module PCB, interference and firmware behavior remain candidate causes.

ToF `raw_mm=255,valid=0` with errors `6`, `7`, or `13` must be discarded from distance calculations; optical invalid frames do not imply I²C NACK. The held hand is not a controlled reference target. Neither **raw ADC counts** nor **raw ToF mm** are validated airway pressure, delivered tidal volume, or infant head/neck angle.

## How to reproduce the stage, without changing the tested firmware

1. **Power OFF before changing sensors or cables.** Preserve the pressure module on physical A2 and ToF on physical B1. Verify exact pin order, compatible 3.3 V breakout input/logic, secure connectors and ground on the real PCB. Do not assume 2023 reference connector numbering applies to another PCB revision. Do not connect ToF to B2's VSYS/5V pin. Keep IMUs disconnected for this isolated check.
2. Use the existing `samd21-pressure-a2-tof-b2` PlatformIO project on this branch. It inherits the already-reviewed firmware; **do not upload just to reproduce these logs** if this same firmware is installed.
3. Open serial monitor (adjust port after `platformio device list` if no longer COM3):

```powershell
cd "$env:USERPROFILE\Documents\KEVIN-a2-b2-review\hardware\sensorhub\samd21-pressure-a2-tof-b2"
$pio = "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe"
& $pio device monitor -p COM3 -b 115200 -f send_on_enter -f log2file
```

4. After a **cold reset** of the hub, type one command at a time (Enter after each): `h` (firmware banner), `c` (both buses), `i` (address-only scan), `s` (ACK check). Only proceed when A2 `0x68` and B1/SERCOM2 `0x29` are the expected addresses. Type `g` to initialize/stream, then `s` to check status. `p` pauses/resumes. `Ctrl+C` closes the host monitor.
5. Run a stationary matte-white target test at a documented distance (e.g. roughly 50 mm) for **60 seconds**, recording valid/invalid ToF frames and any pressure `short_read`, address NACK, or reconnect events. **A successful 30-second sample is not enough to claim long-term reliability.**

**Safety:** Do not hot-plug, push or reseat wires under power. For future analog-response tests, use suitable clean/dry tubing and a controlled low-pressure source only after confirming the **installed** transducer's pressure rating and plumbing. Avoid blowing onto electronics. This is training-simulator bench diagnostics, not clinical use.

## Current acceptance state

| Criterion | Result on 22 Nov 2026 |
| --- | --- |
| A2 I²C address `0x68` detected | **PASS** (intermittent faults later) |
| B1 I²C address `0x29` detected | **PASS**, after wire reseating |
| VL6180X model ID `0xB4` confirmed | **PASS** |
| Both separate SERCOMs returning interleaved rows | **PASS, functionally** |
| Pressure ADC reacts to reported blowing | **Observed signal change**, not calibrated |
| ToF reading during relatively steady hand | **Observed valid stream**, not metrological accuracy |
| Stable pressure I²C over extended run | **OPEN / observed failures** |
| Clinical/physiological calibration and safety | **NOT ATTEMPTED** |

## Next actions

- With all power removed, inspect the pressure A2 cable, locking/keying, contact seating, strain relief and PCB connections. Record exact SensorHub and module revisions.
- Perform an untouched **60-second** concurrent test with a fixed matte-white target and no pressure input. Save the automatically logged `device-monitor-*.log`; calculate counts of valid/invalid ToF frames, I²C NACKs and pressure reconnections. Repeat after power cycles.
- Compare pressure-only `a` to both-buses `c` for the same hardware/wiring, to isolate any bus-interaction effect.
- Confirm fitted pressure sensor part, rail requirements, pressure port connection and safe stimulus limits. Characterize positive/negative pressure with controlled source and calibrated reference **after** transport reliability is improved.
- Preserve tested sources and raw logs; record firmware commit SHA and physical board revision for future acceptance evidence.

Related source history: [review firmware](https://github.com/GabrielleOlivia/K.E.V.I.N/tree/review/samd21-a2-b2-bench/hardware/sensorhub/samd21-pressure-a2-tof-b2) · [older B1 live branch](https://github.com/GabrielleOlivia/K.E.V.I.N/tree/feature/samd21-pressure-a2-tof-b1-live/hardware/sensorhub/samd21-pressure-a2-tof-b1). This record intentionally makes no claim that the earlier B1 branch was flashed during the 22 November test.
