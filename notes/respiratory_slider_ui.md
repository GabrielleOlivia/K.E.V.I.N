# Respiratory pressure slider UI

This tool provides a browser-based live interface for the pressure logger on the
K.E.V.I.N. Raspberry Pi.

It is intended for the current pressure-sensing proof of concept. The two sliders
separate the signed raw pressure delta into:

- **Inhale / positive pressure**: positive ADC delta from the calibrated baseline.
- **Exhale / negative pressure**: magnitude of negative ADC delta from the calibrated baseline.

These labels are for the proof-of-concept interface. The values are **raw ADC
counts**, not calibrated airway pressure, and the system does not yet measure
delivered air volume.

## Firmware requirement

Use the firmware from the pressure-logging work, which continuously outputs:

```text
t_ms,raw,baseline,delta,state,candidate_count,sample_ok,baseline_ok
```

The dashboard also understands the existing `# CANDIDATE_VENTILATION` and
`# NEGATIVE_PRESSURE_END` comment lines.

## Raspberry Pi setup

From the repository root:

```bash
python3 -m pip install -r requirements-ui.txt
```

Connect the SensorHub and confirm it appears as `/dev/ttyACM0`.

Do not run `miniterm` at the same time as the dashboard because only one program
should own the serial port.

Start the dashboard:

```bash
python3 tools/respiratory_slider_ui.py
```

The server listens on port 5000. On the Pi, find its current IP address with:

```bash
hostname -I
```

Then open this from a laptop on the same network:

```text
http://<PI-IP>:5000
```

For example, if the Pi reports `192.168.137.200`, open
`http://192.168.137.200:5000`.

## Controls

The page shows:

- a live positive-pressure slider;
- a live negative-pressure slider;
- current raw ADC delta;
- baseline and raw ADC reading;
- current detector state;
- candidate ventilation count;
- most recently completed positive and negative event peak;
- a **Recalibrate baseline** button, which sends `z` to the SensorHub.

The default slider display range is 0 to 4000 raw counts. This changes only the
visual scale, not the firmware thresholds or sensor behaviour. Override it with:

```bash
python3 tools/respiratory_slider_ui.py --display-max 16000
```

For Windows testing, pass the relevant COM port:

```powershell
python tools\respiratory_slider_ui.py --serial-port COM3
```

## Current limitation

This is a visualization layer, not a clinical ventilation assessment. Pressure
alone cannot determine how much air was delivered to the manikin. A later
respiratory design should combine calibrated pressure with airflow/volume
measurement and the physical lung/chest response.
