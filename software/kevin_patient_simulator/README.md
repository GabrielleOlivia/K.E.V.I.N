# K.E.V.I.N. — Interactive Infant Patient Monitor (training simulator v0.1)

**Runnable Windows desktop software** with synthetic ECG, pleth, respiratory waveform, HR, SpO₂, RR, EtCO₂ and blood pressure. It demonstrates *qualitative interactions* between airway, ventilation, oxygenation, heartbeat and CPR. **It is not a clinical model, vital-sign monitor, diagnosis, device calibrator, or medical control system.**

## Start from GitHub — no ZIP file needed (Windows PowerShell)

This simulator lives in the K.E.V.I.N. repository on the `feature/kevin-interactive-patient-simulator-v0.1` branch, under `software/kevin_patient_simulator`. GitHub stores the code, but because this is a **Python/Tkinter desktop program**, it still runs locally on your computer.

If you have not cloned the repo:

```powershell
cd "$env:USERPROFILE\\Documents"
git clone --branch feature/kevin-interactive-patient-simulator-v0.1 --single-branch https://github.com/GabrielleOlivia/K.E.V.I.N.git
cd ".\\K.E.V.I.N\\software\\kevin_patient_simulator"
py -3 app.py
```

If you already have the project in a local Git checkout, use that checkout instead:

```powershell
git fetch origin
git switch --track origin/feature/kevin-interactive-patient-simulator-v0.1
cd software/kevin_patient_simulator
py -3 app.py
```

The `git switch --track` command is for the **first** checkout of this branch; on later visits simply use `git switch feature/kevin-interactive-patient-simulator-v0.1`. No ZIP extraction is necessary.

Python 3 with Tkinter is required (Python.org Windows installation generally includes Tkinter); the offline virtual simulation has **no external dependencies**.

Python 3 with Tkinter is required (Python.org Windows installation generally includes Tkinter); the offline virtual simulation has **no external dependencies**.

For **real SensorHub serial input**, additionally install:

```powershell
py -3 -m pip install pyserial
```

Close the PlatformIO serial monitor using `Ctrl+C` *before* clicking **Connect COM** in this app: **only one process can own COM3**.

## Modes

| Mode | Description |
| --- | --- |
| **DEFAULT** | Autonomous normal simulated vitals, fake ECG/pleth/resp. Head-angle, pressure and ToF inputs are **ignored**. Instructor can choose an independent demo scenario (Normal / Apnoea / Choking / Cardiac arrest). |
| **SENSOR-REACTIVE** | The supplied **pressure pulses** produce effective/ineffective ventilation, virtual **head pitch** changes the airway, and **ToF motion** registers CPR compressions. HR, SpO₂, EtCO₂ and BP respond *together* via a qualitative demonstration engine. |

### Try it without hardware

1. Select **SENSOR-REACTIVE** and keep **Virtual / interactive** selected.
2. Keep **Auto virtual pressure breaths** enabled: the fake baby receives simulated ventilations and maintains oxygen.
3. Uncheck **Auto virtual pressure breaths**: after **4.5 seconds with no pulse**, the simulation reports apnoea, SpO₂ begins to fall, and HR may initially rise then drop if deterioration continues. **4.5 s is a demo timeout, not a clinical criterion**. Use speed `2.0` or `4.0` to explore the state transitions more quickly.
4. Turn auto breaths on again, then move the head angle to **-50°**: the *toy-model* airway obstructs. Even with delivered pressure breaths, less simulated ventilation reaches the lungs.
5. Move head back to 0° (neutral) to recover oxygenation if no irreversible scenario was selected. This demonstration uses arbitrary angle bands, not clinical angular limits.
6. Press **Deliver simulated compression** repeatedly, or move the ToF slider toward the detector and back. This increases simulated CPR activity; it **does not restore a spontaneous heartbeat** or certify CPR depth.
7. Select **DEFAULT**: physical/virtual controls no longer influence vital signs.

### Physical sensors and assumptions

| Physical port | Module | Data used in this simulator |
| --- | --- | --- |
| A1, Sensor A / SERCOM1 | **one** BHI360 + BMM350 9DoF board | **HEAD** orientation, future `# imu,head_pitch_deg=...` serial frame. **Current SAMD21 v1 bench firmware scans addresses but does NOT output IMU pitch.** A manual head-angle slider is supplied as a temporary fallback even when COM3 is connected. |
| A2, Sensor A / SERCOM1 | MCP3426 pressure ADC | `# pressure,t_ms=...,raw_adc=...,valid=1,pressure_calibrated=0`. Changes relative to a resting baseline register *pressure-pulse events* (training proxy for ventilation). It does **not measure actual airflow**; lack of a pulse is not proof of absent breathing in a real infant. |
| B1, Sensor B / SERCOM2 | VL6180X ToF | `# tof,t_ms=...,raw_mm=...,err=0,valid=1`. Repeated motion relative to a resting distance is treated as **CPR-compression events**. This is not anatomically calibrated chest compression depth. Physical B2 is **not** used. |
| No chest IMU installed | Assumed stationary and horizontal | **Chest pitch fixed at 0°** in software; head pitch is relative to that assumption. Actual head angle needs the BHI360 firmware and axis calibration/zeroing. |

The firmware's confusing log string `bus=B2` names the **shared B SERCOM2 bus**; the ToF physically lives on **B1**. I²C address `0x29` for BHI360 on A and VL6180X on B is valid because these are separate physical buses.

### COM3: what works now

The original `# KEVIN SAMD21 A2+B2 review v1` firmware supports pressure and ToF acquisition via **`g`** after a cold `c`, `i`, `s` scan. It does *not* deliver BHI360 angle measurements. The desktop app can parse its valid pressure and ToF records. Do **not** send `g` if the ToF on B1 has been swapped with an IMU because the firmware would treat `0x29` as the VL6180X.

Before enabling live acquisition, resolve intermittent I²C contacts and the previously observed false ACK bursts (e.g. `0x08`, `0x69`–`0x6F`) and verify the assembled board's power and connector mapping. A single good scan is not a stability pass.

**Live procedure after electrical verification:** power everything off before changing wiring → A1 head IMU, A2 pressure, B1 ToF → use PlatformIO monitor to verify the `c`, `i`, `s` scanner and connector stability first → **close PlatformIO monitor** → select **SENSOR-REACTIVE / Real SensorHub COM3** in this desktop app → **Connect COM** → click **Select c**, then **Scan i** twice (two clean scans are required), optionally **Status s**, and only then **Acquire g**. The app requires explicit confirmation that B1 really has the VL6180X; it will not acquire if the two preceding full scans do not find exactly A=`0x15`, `0x29`, `0x68` and B=`0x29`. Opening COM3 can reset the SAMD21, so the app intentionally offers these manual commands rather than silently issuing them. If live pressure samples are unavailable, the physiology **holds**; it does not infer apnoea from a disconnected sensor.

The original firmware only outputs about 4 pressure samples/s and about 4 ToF samples/s. CPR rates above ~120 compressions/min have undersampling risk; this bridge is a **proof of concept**, not a reliable CPR feedback system.

### Sensor calibration and interpretation

- **Pressure detector:** automatically learns resting ADC count from its first **8** valid raw samples (keep the port quiet). It uses a demo threshold of **180 ADC counts** and a rearm hysteresis. These are unvalidated, dependent on your actual hardware and setup. Pressure sensor is not an airflow meter; the UI reports *pressure-pulse proxy*, not measured respiratory volume or spontaneous breathing.
- **ToF detector:** automatically learns resting distance from **6** valid readings. Set polarity **Closer / Farther** according to mounting direction, then use **Calibrate ToF resting distance** with the manikin untouched. Default demonstration displacement threshold **8 mm**; does **not** represent accurate chest compression depth.
- **IMU:** Head slider uses -60° to +60° in a demonstration convention: negative represents flexion, positive extension, 0° level. No universal medically safe neck-angle threshold exists, and the pitch sign/axis cannot be assumed for a real mounted IMU without orientation calibration. No BHI360 motion driver exists in the v1 diagnostic firmware. An optional future firmware can publish `# imu,head_pitch_deg=-12.5,valid=1` once its sensor fusion implementation is tested.
- **Live simulation speed is locked to 1×:** to avoid mixing real sensor timing with accelerated physiology. Virtual mode supports 1×, 2×, and 4×.
- **No data is NOT no breathing:** the app only begins simulated apnoea when valid pressure samples are arriving but no pulse crosses the chosen threshold. If data becomes stale/disconnected, the physiological state holds and the UI says **PRESSURE SIGNAL UNAVAILABLE**.

### Physiology links (based on the supplied infant-emergency report)

The uploaded reference **“Infant Physiology During Cardiac Arrest, Respiratory Arrest, Positional Airway Obstruction and Choking”** describes these qualitative relationships:

```
head flexion/extension → airway obstruction → poor effective ventilation
pressure pulses + patent airway → effective ventilation → oxygen support
missing/ineffective ventilation → falling oxygenation → early tachycardia
sustained severe hypoxia → bradycardia → possible simulated arrest
ToF repeated compression displacement → simulated low-flow perfusion proxy
arrest + CPR ≠ automatically return of spontaneous circulation (ROSC)
```

The simulator uses *invented illustrative* mathematical rates, thresholds and waveform shapes to make these effects visible. No published physiological timescale, exact HR or SpO₂ prediction, or valid clinical airway threshold is implied. Pulse oximeter values can be unreliable in arrest; this simulator displays **--** for SpO₂ when its artificial arrest state is reached. EtCO₂ disappears if no simulated exhalation or arrest, even if *body CO₂* would increase; the fake display is not a blood-gas measurement. In DEFAULT scenario mode, an instructor can explore independent induced conditions without any sensors.

## Files

- `app.py` — Tkinter monitor GUI, sliders, live mode and event log.
- `engine.py` — deterministic training-only physiology and waveform model.
- `serial_bridge.py` — optional threaded COM3 reader for the unchanged v1 pressure/ToF serial output and optional future head-angle frames.
- `tests/test_engine.py` — regression tests, including data-loss handling and airway interactions.

Run tests:

```powershell
py -3 -m unittest discover -s tests -v
```

## Safety / limitations

The app can send the original SAMD21 firmware's single-character **serial diagnostic commands** (including `c`, `i`, `s`, and `g`) only when the operator explicitly clicks the corresponding control. It does not drive motors, CPR actuators, or medical outputs. Its fake vitals are never real physiological measurements. The source firmware has only been associated with actual bench scans via banner and output, not a verified on-device binary SHA. Treat all numerical thresholds as adjustable educational parameters. Use only with a patient-monitor **training simulator**, never a real infant or patient. Verify electronics independently before physical testing.
