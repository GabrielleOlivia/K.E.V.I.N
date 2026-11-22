# Three-module I²C discovery checkpoint — 23 November 2026 (local time)

## Result and scope

**Observed:** On the real K.E.V.I.N. SAMD21 SensorHub, the user reported one successful I²C address scan with **all three physical sensor modules connected simultaneously**:

- **A1:** one RobotPatient 9DoF IMU board (BHI360 candidate at `0x29` and BMM350 magnetometer candidate at `0x15`), on **Sensor A / SERCOM1**.
- **A2:** MCP3426 pressure ADC candidate at `0x68`, on **Sensor A / SERCOM1**.
- **B1:** VL6180X ToF candidate at `0x29`, on **Sensor B / SERCOM2**.
- **B2:** not in use / not soldered on the user's assembled hardware.

The two independent buses may each have a device at `0x29` without an I²C address conflict. In the existing firmware, log labels `bus=A2` and `bus=B2` refer to the **whole A and B buses**, respectively; the physical ToF port is **B1, not B2**.

**This is a successful discovery/ACK checkpoint, not a stable 3-module measurement, an IMU chip-ID verification, or clinical validation.** The latest log has `tof_initialized=0` (no ranging initialization during that scan) and contains no pressure data or IMU motion data. The IMU does not have a motion-data driver in this firmware.

## Exact serial evidence

**Operator-reported log path (not uploaded to this repository):** `C:\Users\olivi\Documents\KEVIN-a2-b2-review\hardware\sensorhub\samd21-pressure-a2-tof-b2\logs\device-monitor-261123-000052.log`. This file is an evidence excerpt copied from the chat, **not a byte-for-byte copy of the original local .log**. The startup banner and physical results are consistent with the reviewed `A2+B2 review v1` source.

```text
Reconnecting to COM3 ....................................--- Logging an output to C:\Users\olivi\Documents\KEVIN-a2-b2-review\hardware\sensorhub\samd21-pressure-a2-tof-b2\logs\device-monitor-261123-000052.log
         Connected!
# KEVIN SAMD21 A2+B2 review v1
# a=A2 only, b=B2 only, c=both; select once per cold setup
# s=target ACK/status, i=address scan, g=acquire, p=pause/resume, h=help
# STATUS pressure_A2_ack=1 tof_B2_ack=1 tof_initialized=0 pressure_wire=0 tof_wire=0
# SCAN_START bus=A2
# SCAN_FOUND bus=A2 address=0x15
# SCAN_FOUND bus=A2 address=0x29
# SCAN_FOUND bus=A2 address=0x68
# SCAN_END bus=A2 count=3
# SCAN_START bus=B2
# SCAN_FOUND bus=B2 address=0x29
# SCAN_END bus=B2 count=1
# STATUS pressure_A2_ack=1 tof_B2_ack=1 tof_initialized=0 pressure_wire=0 tof_wire=0
```

A `_wire=0` value is I²C transaction success, and `_ack=1` means the configured target address acknowledged. Neither proves that the actual responder is the intended chip without additional register identification and wiring verification.

### Earlier contradictory / unstable evidence (same bench session)

Just before the successful scan, the user reported an **abnormal A-bus scan** with ACKs at `0x08`, `0x09`, and `0x68`–`0x6F` (10 addresses) instead of the expected three A-bus addresses. Pressure ACK changed from `1` to `0` in that session, while ToF on B1 continued acknowledging. In other scans the pressure ADC, IMU board, or ToF disappeared and reappeared. This is a reason to investigate wiring, connector integrity, pull-ups and power; **do not count that abnormal scan as ten devices or assume reliability is solved by this one good scan**. The actual root cause is undetermined.

Earlier in the session, while the pressure module was disconnected, the same IMU board was detected at `0x15` and `0x29` on A1; later it was detected at the same two addresses when moved to B1. Prior pressure + ToF bench testing produced simultaneous raw readings, as recorded in [BENCH_PROGRESS_2026-11-22.md](BENCH_PROGRESS_2026-11-22.md), but the all-three-module configuration has **not yet** been shown to produce synchronized valid sensor measurements.

## Exact firmware preserved

The `src/main.cpp` in this checkpoint is the **same unmodified code** as the earlier `backup/working-pressure-a2-tof-b1-2026-11-22` branch, itself copied from the reviewed diagnostic branch. The main source's historical top comment mentions “No IMUs connected” because it was originally written as a pressure + ToF-only program. The **I²C scanner** is generic and successfully observed the extra A1 IMU responder(s) during the reported physical scan; the **acquisition code supports only pressure and ToF**.

- PlatformIO board: `adafruit_feather_m0_express`
- Serial: COM3, 115200 baud, `send_on_enter`
- A bus: SDA PA16, SCL PA17, SERCOM1 (Feather variant indices 11 and 13).
- B bus: SDA PA12, SCL PA13, SERCOM2 (indices 28 and 39).
- Full scan range: 7-bit `0x08` through `0x77`.
- Menu: `a` select A bus, `b` select B bus, `c` select both; `i` scan; `s` status; `g` starts **pressure + ToF ONLY**; `p` pause; `h` help.
- The exact firmware **binary hash on the SAMD21 was not recorded**. The startup banner `# KEVIN SAMD21 A2+B2 review v1` matches this code.

**Do not confuse this checkpoint with the separate, experimental BHI360 identity-probe branch.** That branch's `m` command is **not** present in this saved working scanner; no Bosch firmware upload or motion/orientation fusion exists here.

## Safely reproducing the I²C scan

1. Before touching any connectors, disconnect USB and **all other power**. Confirm physical A1/A2/B1 harness mapping against the *assembled* board revision. Be particularly careful with five-position connectors that could expose VSYS/5 V; a lit IMU LED alone does not verify its chip supply or signal alignment.
2. With IMU on A1, pressure on A2, ToF on B1 and the wiring verified, power the SensorHub and open the PlatformIO serial monitor:
   ```powershell
   $pio = "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe"
   & $pio device monitor -p COM3 -b 115200 -f send_on_enter -f log2file
   ```
3. After a cold start, send **`c`**, then **`i`**, then **`s`**, each followed by Enter. If the bus stage is already selected, `i` and `s` can be repeated without changing wiring.
4. Expected target *scan* (not a guaranteed output): `0x15`, `0x29`, `0x68` on A and `0x29` on B. Repeat `i` / `s` multiple times to assess short-term repeatability. Stop if extra/implausible addresses or intermittent NACKs return.
5. **Do not send `g` if the ToF is absent or replaced by the IMU on physical B1:** the firmware treats B-bus `0x29` as VL6180X, checks model ID, and may proceed with ToF configuration. Likewise `g` is not IMU initialization. If all expected sensors are present and repeated scans are clean, a later pressure + ToF acquisition test (`g`) can be conducted with separate logging; it still does not measure IMU motion.
6. Stop the monitor with `Ctrl+C`. This does not power off the sensor board.

## Open items before calling it “fully working”

- Verify BHI360 and BMM350 identification registers, not just address ACK.
- Demonstrate pressure and ToF interleaved acquisition with IMU connected, including invalid-frame counts.
- Add separate, carefully tested IMU startup/firmware loading and motion/orientation pipeline.
- Diagnose intermittent address failures and the anomalous many-address scan; measure supply and signal conditions, check harness continuity/pinout and connector reliability.
- Capture source commit and compiled binary hash for future exact firmware traceability, and repeat tests after any firmware changes.
- This project is an infant manikin **training simulator**; no measurements or physiological accuracy are certified for clinical use.

## Related records

- [Original pressure + ToF bench evidence](BENCH_PROGRESS_2026-11-22.md).
- [Historical diagnostic README](README.md) (contains older B2-specific reference instructions; do not confuse B2 with the **physical B1** port used here).
