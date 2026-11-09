# K.E.V.I.N. — Patient scenario simulation (v0.4.0)

## Purpose

This is a **manikin integration test fixture**. It demonstrates how simulated training situations can influence synthetic sensor channels **without changing the sensor registry, transport, protocols, physically measured values or hardware outputs**. It is *not* a medical monitor, neonatal resuscitation algorithm, physiological predictor, ECG simulator for clinical use, or actuator controller.

## Built-in presets

| ID | Educational scenario | Fictional behavior |
|---|---|---|
| `normal` | Baseline | Stylized rhythm, breaths, synthetic SpO2 baseline |
| `cardiac_arrest` | Asystolic arrest | Flat electrical trace, no pulse, no spontaneous breaths |
| `vf_arrest` | VF arrest | Disorganized electrical activity with no effective pulse; no spontaneous breaths |
| `respiratory_arrest` | Apnea | Spontaneous breaths stop while the synthetic cardiac rhythm continues |
| `airway_partial` | Pinched/restricted airway | Partial fictional airflow, larger pressure excursions with effort |
| `airway_complete` | Completely blocked airway | Zero fictional flow despite effort |
| `bradycardia` | Slow rate | Slower synthetic sinus-like rhythm |
| `hypoxia` | Lower oxygen saturation | Lower fictional saturation target |
| `demo` | Existing sensor-fault demonstration | Older simulated I2C/ADC/packet delay and disconnection schedule |

**The numeric values, airway percentage, mock pressure-to-airflow relationship and oxygen trend slopes are arbitrary presentation/test fixtures.** They are neither evidence-based neonatal parameters nor derived measurements. Saturation targets are not reliable SpO2 readings, especially in scenarios without a simulated pulse. The ECG-like waveform is decorative and cannot be transmitted to an actual monitor.

## Interface semantics

The Python `kevin.simulation.patient` module defines a pure, deterministic `patient_state` calculation and a stylized `ecg_trace`. The `Simulator` alone owns simulation scenario selection, airway percentage, simulated ventilation/compressions and synthetic sensor overrides. The manager continues to validate the same sensor messages.

- Scenario changes restart the demo timeline, clear the airway override and turn off simulated interventions; manual overrides for pressure/CPR/SpO2 are removed so the preset actually affects their waveforms.
- `set_airway_obstruction(0..100)` sets a **fictional** restriction parameter. A setting of 100 means zero fictional flow regardless of bag-pressure pulses. **No volume in liters or milliliters is calculated.**
- `set_intervention('ventilation', True)` emits synthetic airway-pressure pulses. Spontaneous respiratory rate remains zero in an apnea scenario. It does not automatically change the SpO2 trajectory or imply effective clinical ventilation.
- `set_intervention('compressions', True)` emits a synthetic CPR force pattern; an arrest scenario retains zero spontaneous heart rate and pulse.
- Pausing synthetic sensor streams tests staleness and connection loss; it is not the same as inducing a patient arrest.
- If a sensor is assigned to a physical source in mixed mode, the simulator cannot take control of that source, even if the patient scenario panel is active. All synthetic patient metrics stay separately identified in `simulated_patient` in `/api/state`.

## API controls

The local (127.0.0.1) dashboard uses the existing `/api/simulation` endpoint and control token. New authenticated request bodies:

```json
{"action":"scenario","scenario":"cardiac_arrest"}
```

```json
{"action":"airway","percent":70}
```

```json
{"action":"airway","percent":null}
```

```json
{"action":"intervention","kind":"ventilation","enabled":true}
```

```json
{"action":"intervention","kind":"compressions","enabled":true}
```

These endpoints can only modify synthetic state. This token is *not suitable* for remote or public access.

## Manual testing checklist

1. Start `python -m kevin --mode simulate`, open `http://127.0.0.1:8765`.
2. Select **Cardiac arrest — asystole**; check the heart rate/respiration values become zero, ECG preview becomes flat, and sensor nodes remain connected.
3. Select **Cardiac arrest — VF**; see an irregular trace with zero effective pulse.
4. Select **Respiratory arrest**; check spontaneous RR=0 and press **Start bag ventilation**; synthetic pressure pulses should reappear but spontaneous RR should stay zero.
5. Select **Pinched airway — partial**; increase restriction toward 100 and check the fictional airflow proxy decreases. Try **Open airway (0%)** to reset restriction.
6. Select cardiac arrest, press **Start chest compressions** and check the simulated force waveform responds without returning a spontaneous pulse.
7. Disable one sensor stream and verify the integration manager marks it stale/disconnected, which is separate from the scenario condition.
8. With real pressure hardware connected in `--mode mixed`, verify scenario controls never overwrite that physical source.

Test suite: `python -m unittest discover -s tests -v` (including `tests/test_patient_scenarios.py`).
