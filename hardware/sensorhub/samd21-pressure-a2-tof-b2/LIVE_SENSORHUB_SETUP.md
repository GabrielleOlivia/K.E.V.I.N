# K.E.V.I.N. experimental real-sensor integration — three physical modules

## Exact bench setup and what is (and is NOT) tested

This is an **opt-in experimental firmware**, separate from the existing unchanged `src/main.cpp`, which produced the actual simultaneous address scan in the **three-module checkpoint**. There is no evidence yet that this *new* firmware builds, uploads, boots the BHI360, publishes valid pitch, or produces reliable real-time CPR events on the actual board. Never confuse a passing I²C scan with working motion sensing.

Physical sensor and logical connections:

| Physical port | Module | Internal I²C bus | 7-bit address |
| --- | --- | --- | --- |
| **A1** | RobotPatient BHI360 (+ separate BMM350 chip) | SERCOM1 PA16/PA17 | BHI360 `0x29`, BMM350 `0x15` |
| **A2** | MCP3426 pressure ADC | SERCOM1 PA16/PA17 | `0x68` |
| **B1** | ST VL6180X ToF | SERCOM2 PA12/PA13 | `0x29` |
| B2 | Not connected/soldered | SERCOM2 | — |

The legacy firmware prints `bus=A2` for all of **Sensor A**, and `bus=B2` for all of **Sensor B**. Those output labels do **not** mean physical B2. The chest reference is **assumed stationary and horizontal**; only one IMU is installed, on the head. The relative pitch sign and reference are **not universal**: first neutralize with `z`, observe known head flexion, then reverse the sign with `f` if necessary. If the IMU is mounted sideways, use `j` to select roll instead of pitch, then `z` again. **No universal head angle reliably diagnoses an obstructed infant airway.** The software uses demonstration bands, not medically validated thresholds.

## Firmware files, provenance and dependencies

- `src/main.cpp`: untouched, physically bench-tested diagnostic (`A2+B2 review v1`).
- `src/main_live.cpp`: **new experimental** Bosch BHI360 FIFO/Euler code, preserving v1 pressure and ToF logic but increasing polling to nominal pressure 150 ms, ToF 100 ms. Those new rates have **not** been bench tested.
- `platformio.ini`: separate environment `kevin_live_sensors`. Default firmware environment continues to compile `main.cpp`.
- `scripts/vendor_bhi360.py`: explicitly clones Bosch's public [BHI360 SensorAPI](https://github.com/boschsensortec/BHI360_SensorAPI), copies all library source files, the **Bosch_Shuttle3_BHI360_bsxsam.fw.h** firmware header and the BSD-3-Clause license into ignored local `lib/BHI360Vendor`. It records the exact upstream Git commit used. This is required because the BHI360 host cannot produce Euler orientation simply by acknowledging I²C.

Build and flash only after the electrical connector mapping has been verified and the I²C scan is repeatedly clean. Important: the actual SensorHub may have unverified five-contact power arrangements. **Never move/plug/unplug cables while any power is connected.** The IMU LED alone doesn't prove the BHI360's supply level or correct data wiring. Do not use this setup on a patient.

### Windows PowerShell (in the cloned repo)

```powershell
cd "$env:USERPROFILE\Documents\KEVIN-Live\hardware\sensorhub\samd21-pressure-a2-tof-b2"
$pio = "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe"

# No firmware upload: download the required Bosch source from its official GitHub
py -3 scripts/vendor_bhi360.py

# Compile experimental firmware on your PC, check RAM/flash report; this does NOT flash
& $pio run -e kevin_live_sensors
```

If that build fails, **stop** and preserve the log. Don't use the upload command. The Bosch library and firmware are substantial; RAM and flash capacity must be checked on your actual SAMD21. Only if it builds without errors and the wiring is verified, decide whether to opt into flashing:

```powershell
# Only if you explicitly choose the EXPERIMENTAL IMU firmware after reviewing risks
# Stop all serial monitor/app connections before flashing
& $pio run -e kevin_live_sensors -t upload --upload-port COM3
```

**Rollback:** Restore the proven firmware without changing wiring, first with all external peripherals disconnected and with the correct COM port confirmed:

```powershell
& $pio run -e adafruit_feather_m0_express -t upload --upload-port COM3
```

If anything reports `STOP`, `IMU_FAULT`, or repeated unexpected addresses, cease tests, unplug power before touching sensors, and preserve the output.

## Experimental firmware command order

Start with *all three modules connected* and the board cold-restarted. In PlatformIO Serial Monitor (or the Python app), issue each command followed by Enter. Commands require the selected bus to be initialized once per cold boot.

1. `c` — select both I²C buses.
2. `i` — scan both buses; expected Bus A `0x15,0x29,0x68`, Bus B `0x29`.
3. `i` — scan again; **both scans** must have only those expected addresses.
4. `s` — status; pressure and ToF ACK 1.
5. `m` — **experimental Bosch BHI360 firmware upload and Euler stream startup**. Wait for `# IMU_READY...`, then `# imu,head_pitch_deg=...,valid=1`. This involves soft-resetting and loading on-chip BHI360 firmware, **not** reflashing the SAMD21 itself. It may fail until the Bosch library and board connection issues are resolved. Do not claim it is active merely from an `IMU_READY` message; verify several angle frames change with movement.
6. Hold the head in its intended neutral reference and issue `z` to zero the displayed relative pitch. Move it gently in a known flexion direction. If flexion causes a *positive* value while the simulation convention expects *negative*, enter `f` once to reverse the sign. If physical flexion rotates the sensor's **roll** axis rather than pitch, enter `j` to select roll, then re-zero with `z`.
7. Only after the IMU has been verified and the physical **B1 is confirmed to contain the ToF**, issue `g` to start the pressure ADC and ToF distance acquisition.
8. Close PlatformIO Serial Monitor with `Ctrl+C`, launch the Python app, and use the app's buttons to repeat the stage after a USB reset. **COM3 cannot be held by both programs simultaneously.**

The app has manual controls for `c / i / s / m / z / f / j / g` and prevents starting `m` or `g` until two clean scans. **The scan requirement is a software check, not sufficient proof of safe wiring or calibration.** Only select Real SensorHub COM3 in SENSOR-REACTIVE mode. Default mode deliberately ignores hardware.

## Live physical interactions

- **Blow/pressure:** the app listens to `# pressure,t_ms=...,raw_adc=...,valid=1,...`; keep the pressure port quiet while the first eight valid samples establish an idle baseline. A rising excursion beyond the *toy* 180-count threshold registers a **pressure-breath event**. A pressure event is NOT a measurement of airflow volume, and zero events only implies no detected pressure pulses during a healthy, calibrated signal stream. In simulator-reactive mode, this is treated as missing effective ventilation after an illustrative delay and changes simulated SpO₂, HR, RR, EtCO₂, and ECG.
- **Move your hand / CPR ToF:** the app listens to valid `# tof,t_ms=...,raw_mm=...,err=0,valid=1`. After six stable baseline readings, move a target at least ~8 mm towards the sensor (or select Farther) then return to baseline between events; each valid in/out stroke registers a **ToF compression-proxy event** in the added CPR trace. The VL6180X does NOT measure chest compression depth in this setup and hand gestures are not medical CPR evidence.
- **Tilt head IMU:** after a successful Bosch firmware upload and orientation FIFO stream, `# imu,head_pitch_deg=...` changes the virtual airway effectiveness. It is a demonstration mapping and depends on mount-axis calibration and zeroing. This firmware has **not** been physically tested yet.
- **Missing data:** the monitor holds its physiological state and marks `PRESSURE SIGNAL UNAVAILABLE` or `HEAD IMU SIGNAL UNAVAILABLE`; **a sensor disconnect must not be interpreted as respiratory arrest or a normal head angle**. To test only pressure+ToF without IMU firmware, the app has an explicit `Allow manual head fallback` checkbox, OFF by default.

### Limitations and next validation

- Real pressure and ToF are not clinically calibrated; original v1 output was ~4 samples/s per sensor, so brief breaths and high-rate gestures may be missed. The new experimental live firmware's faster sample cadence must be confirmed on hardware and may still be inadequate for accurate CPR rate/depth.
- BHI360's Euler sensor requires Bosch SDK upload, compatible firmware image, and a correct device mounting orientation; chip ID alone is insufficient. Sensor fusion boot may take a while. Do not move wiring while powered.
- There was an earlier abnormal ten-address scan on Sensor A and intermittent NACKs. One successful four-address scan **does not establish long-term reliability**. Check connector alignment, 3.3-V rails, grounds, and pull-up arrangements using a multimeter before live multichannel acquisition.
- Simulator cardiovascular reactions are artificial educational sequences based on the uploaded infant-physiology reference, not time-accurate predictions of a real infant emergency.

**References:** [Bosch official BHI360 SensorAPI](https://github.com/boschsensortec/BHI360_SensorAPI), [Bosch BHI360 datasheet](https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bhi360-ds000.pdf), [previous verified three-module I²C scan](THREE_MODULE_I2C_CHECKPOINT_2026-11-23.md).
