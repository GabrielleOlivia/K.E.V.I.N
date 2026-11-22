# K.E.V.I.N. Live Physical Sensors — desktop simulator v0.2

**What is available now:** This monitor reads real serial frames produced by your already-tested SensorHub pressure and ToF firmware, detects positive pressure pulses as training "breaths", and registers repeated changes in physical B1 ToF distance as **CPR proxy events** (with a separate CPR waveform and rate). Both affect the same simulated patient state, not isolated widgets. The original firmware has **not** been rewritten or overwritten.

**Head IMU is experimental:** The old SensorHub firmware only discovers the BHI360 address; it does NOT publish head pitch. The new separate opt-in `kevin_live_sensors` firmware environment contains an *unbuilt and hardware-untested* Bosch SensorAPI firmware-upload/Euler streaming implementation. See [SensorHub live build and risk notes](../../hardware/sensorhub/samd21-pressure-a2-tof-b2/LIVE_SENSORHUB_SETUP.md). **Do not claim real head-tilt control is working until the Bosch firmware boots and `# imu,head_pitch_deg=...,valid=1` changes when you physically tilt it.**

### Use the real sensors from the desktop GUI

1. Verify the wiring *unpowered*: head IMU on A1, MCP3426 pressure on A2, VL6180X ToF on physical **B1**. Do not hot-plug, and investigate earlier anomalous I²C scans before combined live acquisition.
2. Install `pyserial` (once): `py -3 -m pip install pyserial`. Close PlatformIO Serial Monitor (`Ctrl+C`) so the GUI can open COM3.
3. Run `py -3 app.py`, select **SENSOR-REACTIVE** then **Real SensorHub COM3**, click **Connect COM**.
4. Click **Select c**, then **Scan i** twice. Both scans must show Bus A (`0x15`, `0x29`, `0x68`) and Bus B (`0x29`) and no extra addresses; use **Status s** to confirm ACKs. The app blocks acquisition until two clean scans.
5. For the new **experimental live SensorHub firmware only**, click **Start IMU m** to upload Bosch firmware, then confirm that live head angles appear. With the head physically neutral, click **Zero tilt z**. Tilt it gently and make sure forward flexion corresponds to *negative* angle values; **Flip tilt f** reverses the sign if required. If the physical bending appears as roll instead of pitch, use **Axis j** to select the other axis, then re-zero with the head neutral. If the IMU fails, the GUI displays **HEAD IMU SIGNAL UNAVAILABLE**, and does **not** silently assume 0°. You may explicitly choose **Allow manual head fallback** to demonstrate pressure/ToF before IMU orientation works.
6. Click **Acquire g** only when the actual B1 device is the VL6180X ToF. Leave the pressure port at rest for the first eight valid samples (~1–2 s for the experimental faster firmware, ~2 s with v1); then blow or apply a known safe pressure pulse and watch the event log and simulated respiratory waveform/SpO₂/HR. This detects *positive pressure change*, **not measured airflow**.
7. Hold your hand stationary in front of the ToF for six valid samples to establish the resting distance. Move toward the ToF by more than the demonstration ~8 mm threshold, then return it to rest. Each approach-and-release can register one **CPR proxy event**, with CPR waveform activity shown in red. If the ToF is mounted so compressions move **away**, choose **Farther** and recalibrate at rest. **This is not calibrated CPR depth or a medical CPR monitor.**
8. Choose **DEFAULT** to ignore *all* live sensors and show independently generated healthy/emergency scenarios.

### Troubleshooting

- **No COM3**: close PlatformIO monitor; make sure `pyserial` is installed; reconnect USB only when no wires are being moved; use the port shown by `platformio device list`.
- **Pressure values but no breath**: sensor readings must be `valid=1` and rise above the quiet baseline by the unvalidated threshold of 180 ADC counts. Verify the raw values change when you apply a pulse and keep the port quiet for initial calibration. Very short pulses may be missed by the existing firmware's ~4 Hz sampling.
- **ToF values but no CPR**: ensure there are six *valid* resting range values; move in the chosen polarity and fully return to the baseline between events. High-speed real CPR is undersampled by existing v1 firmware.
- **IMU I²C addresses appear but head angle shows NO DATA**: this is normal with old firmware. A matching address is **not** a streaming orientation sensor. Don't flash the experimental firmware without checking its compile result and the hardware connection stability.
- **Any sensor stops sending data**: the model holds physiology instead of diagnosing apnoea or a normal head position from stale data. The underlying model's rates/angles are illustrative and not clinical thresholds.

---

# K.E.V.I.N. — Interactive Infant Patient Monitor (training simulator v0.1)

**Runnable Windows desktop software** with synthetic ECG, pleth, respiratory waveform, HR, SpO₂, RR, EtCO₂ and blood pressure. It demonstrates *qualitative interactions* between airway, ventilation, oxygenation, heartbeat and CPR. **It is not a clinical model, vital-sign monitor, diagnosis, device calibrator, or medical control system.**

## Start in 2 steps (Windows PowerShell)

Extract this ZIP. In the extracted `kevin_patient_simulator` directory run:

```powershell
py -3 app.py
```

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

This code never sends commands to the SAMD21 or drives motors, CPR actuators, or medical outputs. Its fake vitals are never real physiological measurements. The source firmware has only been associated with actual bench scans via banner and output, not a verified on-device binary SHA. Treat all numerical thresholds as adjustable educational parameters. Use only with a patient-monitor **training simulator**, never a real infant or patient. Verify electronics independently before physical testing.
