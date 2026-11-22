# Experimental third sensor: ONE BHI360 IMU on physical A1

**Status (22 November 2026): source prepared in a separate GitHub branch; this revision has NOT been built, uploaded, or bench-tested.**

This continues the **hardware-tested** [two-sensor baseline](BENCH_PROGRESS_2026-11-22.md) and adds a **manual, read-only** identity command for a single BHI360 IMU. It does **not** initialize BHI360 motion streams or produce acceleration, gyroscope, magnetic, fusion, quaternion or neck-angle values. Those features remain future work because the earlier Bosch firmware-boot experiments experienced a startup/crash problem.

> **Code review correction (22 Nov):** Bosch's BHI360 host I²C address is **0x28 with HSDO low** or **0x29 with HSDO high**. The tested v1 `i` scanner already checks both addresses: the user's actual Bus A scan found only `0x68` (pressure) with all three boards connected. The LED lighting up is not an I²C ACK. The *experimental* `m` command now checks both `0x28` and `0x29`, refuses to read IDs if both ACK (ambiguous), and attempts identification only for a unique ACK. **This is a software diagnostic enhancement, not a fix for the missing IMU ACK.** The experimental branch remains unbuilt and untested. Do not flash it merely to make an absent address appear.

## Physical topology

| Physical socket | Module | I2C | Address | Tested state |
| --- | --- | --- | --- | --- |
| **A2** | MCP3426 pressure ADC | SERCOM1, PA16 SDA / PA17 SCL | `0x68` | Previously tested, but intermittent pressure NACKs |
| **A1** | One BHI360-based IMU, provisional chest/head role | **Same SERCOM1 shared with A2** | `0x29` | **Not yet tested simultaneously with A2 pressure + B1 ToF** |
| **B1** | VL6180X ToF | SERCOM2, PA12 SDA / PA13 SCL | `0x29` | Previously tested |
| **B2** | UNUSED / not soldered | SERCOM2, shared with B1 | — | Unused |

The `0x29` on **A1** and `0x29` on **B1** do not collide because they are on **different hardware I²C buses**. A1 `0x29` and pressure A2 `0x68` also coexist on the **same** bus because their addresses differ. The code's existing `bus=A2` scan means *all devices on bus A*, including A1; its `bus=B2` scan means *all devices on bus B*, including the physically connected ToF on B1. These are historical bus labels, NOT the actual physical port locations.

**Electrical safety gate: A1 is a five-contact socket in the 2023 reference design and exposes an additional VSYS supply contact.** It cannot be treated as an ordinary four-pin port. The user's actual SensorHub is an older revision and the exact physical contact orientation must be checked on that actual PCB; a loose/misaligned four-wire jumper could connect a logic or power line to VSYS. Do not connect or power an IMU until the real socket, harness, sensor carrier supply and logic-level compatibility are verified with all power disconnected. Use the previously validated A1 IMU harness only if its wiring has been independently checked. Avoid adding pullups or 5 V. Also secure the earlier intermittent jumper contacts before reliability testing.

The prior project [`feature/pressure-imu-integration`](https://github.com/GabrielleOlivia/K.E.V.I.N/tree/feature/pressure-imu-integration/hardware/sensorhub/pressure-imu) identified BHI360 modules at `0x29` and used read-only BHI360 registers. This new experiment reuses the safe identity approach but **keeps the successful two-sensor measurement loop** instead of transplanting the older blocking pressure logic.

## Stage 1: hardware ACK scan with already-tested firmware (NO firmware change yet)

1. With all power OFF, leave pressure on A2, leave ToF on B1, and connect only **one** correctly wired/voltage-compatible IMU to **A1**. Leave B2 and other peripherals unused. Check for wire-to-wire shorts and verify intended power/ground at the sensor end with the IMU disconnected before final attachment; disconnect power for each wiring change.
2. Reconnect USB and open the existing reviewed diagnostic on the board (banner `# KEVIN SAMD21 A2+B2 review v1`). In Windows PowerShell from the existing PlatformIO project:

```powershell
$pio = "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe"
& $pio device list
& $pio device monitor -p COM3 -b 115200 -f send_on_enter -f log2file
```

3. Type `c` Enter, `i` Enter, `s` Enter. This is an **address-only** check. Do **not** enter `g` before inspecting the addresses.

```text
# SCAN_START bus=A2
# SCAN_FOUND bus=A2 address=0x29
# SCAN_FOUND bus=A2 address=0x68
# SCAN_END bus=A2 count=2
# SCAN_START bus=B2
# SCAN_FOUND bus=B2 address=0x29
# SCAN_END bus=B2 count=1
# STATUS pressure_A2_ack=1 tof_B2_ack=1 tof_initialized=0 pressure_wire=0 tof_wire=0
```

**This is a predicted result, NOT an observed test.** If either expected address is absent, an unexpected address responds, or the controller stops responding, stop, save the log, disconnect power, and debug wiring/supply. **Note:** `s` checks only pressure and ToF; it does not report IMU identity.

## Stage 2: optional BHI360 identity test (NEW firmware, NOT yet tested)

After stage 1 succeeds, you may build this experimental branch in a **separate local Git worktree** and upload only after the build succeeds and with Serial Monitor closed. Do not overwrite the historical working binary without recording the working commit. The code adds one new serial command:

- `m` — probe the **one** BHI360 expected on **A1**. It first checks an ACK on Sensor A `0x29`, then reads the documented FUSER2 ID register `0x1C` (expected `0x89`) and chip ID register `0x2B` (expected `0x7A`). If both match, it reads revision `0x1D`, boot status `0x25`, and error value `0x2E`. No Bosch firmware upload, reset, or motion configuration is performed.
- Existing `a`, `b`, `c`, `i`, `s`, `g`, `p`, `h` commands remain.

To set up without changing your existing review worktree:

```powershell
$repo = "$env:USERPROFILE\Documents\K.E.V.I.N"
$work = "$env:USERPROFILE\Documents\KEVIN-a1-imu-probe"
git -C $repo fetch origin
git -C $repo worktree add --detach "$work" origin/feature/samd21-a2-pressure-b1-tof-a1-bhi360-probe
cd "$work\hardware\sensorhub\samd21-pressure-a2-tof-b2"
$pio = "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe"
& $pio run -e adafruit_feather_m0_express
```

If build succeeds, close all monitors, disconnect sensors and other external supplies with power off, and upload the diagnostic to the hub alone using `& $pio run -e adafruit_feather_m0_express -t upload --upload-port COM3` after confirming the actual COM port. Reattach sensors with **all power off** and reconnect USB. On startup, the expected new banner is `# KEVIN SAMD21 A2-pressure B1-ToF A1-BHI360-probe v2 (UNTESTED)`.

Then type `c`, `i`, `s`; after address checks pass, type `m`.

```text
# IMU_A1_ACK bus=A1_shared_A2 address=0x29 wire_status=0 ack=1
# IMU_A1_ID fuser=0x89 chip=0x7A identified=1 motion=UNAVAILABLE
# IMU_A1_HEALTH revision=0x... boot=0x... error=0x...
# IMU_A1_NO_FIRMWARE_UPLOAD orientation=UNAVAILABLE
```

**Expected format only; not a hardware result.** If `identified=0`, no further registers are queried. `motion=UNAVAILABLE` means the sensor has **not** been configured to stream motion; never report a 0° neck angle as though it were measured. Preserve errors and raw output if any register read fails. Once the IMU ID is good, `g` may be used to evaluate pressure + ToF stream concurrency. The `m` probe is manual and does not attempt to stream IMU data.

## Remaining work / exit criteria

1. Show all three addresses in an address-only scan in a single wiring configuration, with no unexplained NACKs.
2. Read correct BHI360 IDs and status at A1 without disturbing simultaneous pressure and ToF output.
3. Reproduce a 60-second untouched run; record pressure `short_read`, reconnect and ToF valid/invalid frame counts. Previous pressure transport errors are still unresolved.
4. Resolve the historical BHI360 firmware-boot issue *separately* and safely before enabling orientation/accelerometer/gyro or calibration. A **single** IMU could give orientation *relative to an initial reference frame*, but **head relative to chest** requires the second IMU or another reference.
5. Record cable mapping, board revisions, exact firmware SHA, log paths, and pass/fail data. This setup is a training simulator, not a clinical device.

