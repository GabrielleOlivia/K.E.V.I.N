# K.E.V.I.N. pressure sensor demonstration

## Purpose

A presentation-focused browser UI for the existing SAMD21 + MPXV5010GP + MCP3426 proof of concept. Intended for non-technical visitors while retaining raw engineering measurements and event states.

This is a **pressure-only** demonstration. Do not claim that this measures delivered tidal volume, breathing effectiveness, patient safety, or calibrated airway pressure.

## Before the session

If the existing firmware/dashboard was working recently, **do not reflash the SAMD21** just to use this UI. This is a Python-only addition that understands the pressure-logging firmware's existing 8-column CSV output:

\`\`\`text
t_ms,raw,baseline,delta,state,candidate_count,sample_ok,baseline_ok
\`\`\`

### Run with SAMD21 on Windows

From the repository root (folder containing \`platformio.ini\`):

\`\`\`powershell
python -m pip install -r requirements-ui.txt
python -m serial.tools.list_ports -v
python tools\pressure_presentation_ui.py --serial-port COM3
\`\`\`

Use the actual COM port if different from COM3. Open \`http://127.0.0.1:5000\` in Edge or Chrome and press **F11** or the dashboard **Full screen** button.

Important: close PlatformIO Serial Monitor, miniterm, and the old dashboard first. Only one application can own the USB serial port. Opening a new serial connection may reset the SAMD21. After connection, place the sensor at rest and click **Calibrate sensor** once. The baseline remains fixed until you explicitly recalibrate or reset firmware.

### Backup: simulated demo without hardware

\`\`\`powershell
python tools\pressure_presentation_ui.py --demo
\`\`\`

Open \`http://127.0.0.1:5000\`. A prominent **SIMULATED DEMO · NO SENSOR** banner is shown. Every reading is artificial and must be presented as simulation, not a physical test.

### Adjust visual range

The dashboard starts at ±8,000 raw ADC counts for presentation visibility. Select ±2,000, ±8,000, ±16,000, or ±32,000 from the **Visual scale** menu. When a response exceeds the visual scale, the bar/graph clips but the numeric raw delta remains correct. Choosing another visual range does **not** change sensor sensitivity or event thresholds.

### Rehearsal checklist

1. Connect pressure module to the already verified SensorHub Sensor A2 wiring with power off; connect SAMD21 USB cable.
2. Check \`python -m serial.tools.list_ports -v\` for your real board. Previous tests used \`COM3\`, USB VID:PID \`239A:801B\`.
3. Start the UI; confirm the top badge says **LIVE SENSOR**, not **SIMULATED DEMO**.
4. Click **Calibrate sensor** with pressure at rest. Wait for **Sensor ready** and a populated baseline.
5. Apply a gentle positive pressure test and look for the green pressure-increases indicator.
6. Pull gently/return the syringe and watch the blue pressure-decreases indicator.
7. Expand **Engineering details** when explaining the SAMD21, raw ADC delta, calibration, and event thresholds.
8. If the hardware stops working, use the clearly labeled simulated mode and say the hardware is unavailable.

Avoid high pressure/strong vacuum, forceful syringe pushes, or sealing/occluding the sensor without confirming a safe pressure relief path.

## Suggested 20-second explanation

“We’re developing a training manikin that will eventually respond to the way a nurse ventilates it. Today, this sensor can detect changes in pressure. When I apply pressure the green bar and waveform move, and when the pressure decreases the blue bar moves. The SAMD21 measures and sends the data to this laptop. We still need airflow measurement and calibration before we can say how much air was delivered or whether a ventilation was effective.”

## Known limitations

- Direction is the sign of the raw pressure change, **not measured inhalation/exhalation**.
- Calibration is a resting ADC baseline; the signal is not converted to clinically meaningful pressure units.
- Event count is a provisional positive-pressure event count. The detector can double-count certain transients, and cannot validate real breaths.
- COM port may change when uploading/rebooting the SAMD21.
- Raspberry Pi is not required for this laptop-only version.
- The dashboard does not actuate anything or simulate a real patient monitor.
