# K.E.V.I.N. — Interactive integration lab

This is a **synthetic bench testing interface**, not a patient monitor or controller for physical sensor modules. The integration manager, real adapters and legacy SAMD21 pressure firmware remain separate from browser controls.

## Run and interact

From the project root:

```sh
python -m kevin --mode simulate
```

Open `http://127.0.0.1:8765`. The browser shows six test channels, an overall control panel, connection diagnostics and derived relative IMU rotation. Each simulated card supports:

- **Enable synthetic stream:** uncheck to stop the stream. Watch the manager mark its last reading stale, then disconnected. Recheck to recover.
- **Manual test value:** move the slider to emit a fixed synthetic value. For head/chest IMU cards the slider sets rotation around the simulator Y axis; both use the same synthetic frame so relative rotation can be compared. The sliders do *not* claim any clinical, physiological, or anatomical measurement.
- **Auto waveform:** clear the manual override and resume its synthetic waveform generator.

The global panel supports:

- **Pause/resume all simulated streams**, allowing timeout and recovery testing without altering real sources.
- **Scenario selection:** `normal`, `demo`, `cardiac_arrest`, `vf_arrest`, `respiratory_arrest`, `airway_partial`, `airway_complete`, `bradycardia`, or `hypoxia`. Switching resets only the selected fault-scenario timeline. `demo` causes a head-message delay near 3–4 seconds, SpO2 silence near 4–11 seconds, and invalid pressure readings near 6–8 seconds.
- **Reset manual values** to clear test overrides.

## Tomorrow: mixed mode

When you have the existing pressure module, run `python -m kevin --mode mixed --pressure-port COM3` (or the Pi serial path). The pressure card reports `PHYSICAL INPUT` and has no simulation controls. The remaining cards can still be simulated and controlled. The browser is prohibited from overwriting a physical feed.

## Control safety model

`/api/simulation` is available only when simulation is running. A per-process token is delivered through the local state API and must be included as `X-KEVIN-Token` in POST requests. It is a simple accidental-control guard, **not** security appropriate to a public deployment. The HTTP server is bound to `127.0.0.1` by default. Do not port-forward or publish it to other systems.

Controls are whitelisted and validated. Slider limits are only **demonstration ranges**, not clinical targets or alarms. The manager remains responsible for accepting messages, rejecting malformed values, ordering by sequence, tracking timing and deriving state.

## Automated tests

```sh
python -m unittest discover -s tests -v
node --check kevin/web/app.js
```

`tests/test_interactive_controls.py` validates manual overrides, quaternion normalization, synthetic pause/timeout/recovery, scenario reinitialization, API input validation, invalid tokens and controls limited to the simulation owner. The JavaScript syntax check does not validate rendering. `tools/verify_dashboard.py` can check real browser behavior on a machine with unrestricted Chromium loopback access.

## Patient scenario lab (v0.4.0)

A separate synthetic patient panel supports cardiac arrest (asystole or ventricular fibrillation), respiratory arrest, partial/complete airway obstruction, low heart rate, and low saturation. The panel has a stylized electrical heart trace and four **fictional** metrics (heart rate, spontaneous respiratory rate, SpO2 target and airflow proxy). These are not physical measurements or a validated physiology/ECG model.

- **Airway slider (0–100%)** changes a fictional resistance proxy. **Open airway** sets it to zero. **Use scenario default** clears the override. Physical sensors are never affected.
- **Start bag ventilation** adds synthetic bag-pressure pulses and synthetic airflow when the fictional airway is open, but it does not restore spontaneous breathing.
- **Start chest compressions** adds synthetic compression-force pulses but never restores the simulated heart rate.
- Selecting a new patient preset resets interventions and patient-dependent pressure/SpO2/CPR manual overrides. Independent head/chest orientation overrides are retained.
- The original individual sensor stream toggle, pause and raw-value sliders still work. A manual pressure, CPR, or SpO2 slider explicitly overrides the scenario-generated synthetic channel until cleared.
- In mixed mode, a physical pressure adapter remains independent; scenario controls **cannot** overwrite it. Do not compare the fictional airflow proxy to real delivered air volume.

See [patient scenarios and limitations](PATIENT_SCENARIOS.md) and run `python -m unittest discover -s tests -v` to exercise the scenario boundary.
