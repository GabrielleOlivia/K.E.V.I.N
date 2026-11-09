"""Illustrative manikin scenarios. Deliberately NOT a physiological or clinical model.

Patient state is separate from sensor acquisition. In mixed mode, these values
NEVER overwrite physical sensor channels or create authenticated node messages.
"""
import math


# Labels are intentionally specific about what is actually being demonstrated.
SCENARIOS = {
    'normal': ('Normal training baseline', 'Stable synthetic vitals and unobstructed airway.'),
    'cardiac_arrest': ('Cardiac arrest — asystole', 'No simulated pulse; flat electrical trace and apnea.'),
    'vf_arrest': ('Cardiac arrest — VF', 'No simulated pulse despite disorganized electrical activity.'),
    'respiratory_arrest': ('Respiratory arrest', 'No spontaneous breaths; synthetic heart activity continues.'),
    'airway_partial': ('Pinched airway — partial', 'Restricted synthetic airflow with increased airway-pressure proxy.'),
    'airway_complete': ('Airway blocked — complete', 'No synthetic airflow through the airway despite pressure pulses.'),
    'bradycardia': ('Low heart rate', 'Slower synthetic heart rhythm; not an age-specific threshold.'),
    'hypoxia': ('Low oxygen saturation', 'Illustrative lower oxygen saturation without a specific diagnosis.'),
    'demo': ('Sensor communication fault demo', 'Original link/ADC fault timeline; patient baseline otherwise normal.'),
}

AIRWAY_DEFAULTS = {'airway_partial': 65, 'airway_complete': 100}


def _pulse(t, frequency_hz):
    if frequency_hz <= 0:
        return 0.0
    return max(0.0, math.sin(2*math.pi*frequency_hz*t))


def patient_state(scenario, elapsed_s, airway_override=None,
                  compressions=False, ventilating=False):
    """Compute an operator-visible *fictional* state without hidden feedback loops.

    Values are demo fixtures, not recommended clinical settings or outcomes.
    In particular, turning on CPR does NOT restore spontaneous circulation.
    """
    if scenario not in SCENARIOS:
        raise ValueError('unknown scenario')
    if not math.isfinite(elapsed_s) or elapsed_s < 0:
        raise ValueError('scenario clock must be nonnegative finite')
    if airway_override is not None and (type(airway_override) not in (int, float) or
                                        not math.isfinite(airway_override) or
                                        not 0 <= airway_override <= 100):
        raise ValueError('airway obstruction must be 0..100 or null')
    airway = float(AIRWAY_DEFAULTS.get(scenario, 0) if airway_override is None else airway_override)
    no_circulation = scenario in ('cardiac_arrest', 'vf_arrest')
    no_breathing = scenario in ('cardiac_arrest', 'vf_arrest', 'respiratory_arrest')
    hr = 0 if no_circulation else 65 if scenario == 'bradycardia' else 130
    rr = 0 if no_breathing else 35
    # A deliberately simple operator-authored trend: these curves are NOT
    # neonatal physiology and cannot predict desaturation or intervention effect.
    trend_per_second = {
        'normal':0, 'demo':0, 'cardiac_arrest':1.2, 'vf_arrest':1.2,
        'respiratory_arrest':0.5, 'airway_partial':0.23,
        'airway_complete':0.7, 'bradycardia':0.05, 'hypoxia':0,
    }[scenario]
    spo2 = (88 if scenario == 'hypoxia' else 97) - min(50, trend_per_second*elapsed_s)
    spo2 = round(max(0, spo2), 1)
    # One fictional mechanical effort indicator, not airflow or volume in SI units.
    effort = bool(rr > 0 or ventilating)
    flow_pct = 0.0 if not effort else round(max(0, 100-airway), 1)
    rise_pct = flow_pct
    return {
        'scenario': scenario,
        'name': SCENARIOS[scenario][0],
        'description': SCENARIOS[scenario][1],
        'elapsed_s': round(elapsed_s, 2),
        'heart_rate_bpm': hr,
        'spontaneous_resp_rate_bpm': rr,
        'spo2_target_percent': spo2,
        'rhythm': 'asystole' if scenario == 'cardiac_arrest' else 'vf' if scenario == 'vf_arrest' else 'sinus_like',
        'pulse_present': hr > 0,
        'airway_obstruction_percent': airway,
        'airway_override_active': airway_override is not None,
        'ventilation_on': bool(ventilating),
        'compressions_on': bool(compressions),
        'airflow_proxy_percent': flow_pct,
        'chest_rise_proxy_percent': rise_pct,
        'is_synthetic': True,
        'warning': 'Illustrative training curves only; not actual patient physiology, flow or delivered volume.',
    }


def pressure_proxy(t, state, rng):
    """Arbitrary synthetic ADC-count waveform (no pressure calibration)."""
    natural = _pulse(t, state['spontaneous_resp_rate_bpm']/60)
    bag = _pulse(t, 0.4) if state['ventilation_on'] else 0.0
    # During obstruction, the same fictional effort creates a larger pressure
    # excursion even though the fictional airflow proxy becomes smaller.
    effort = max(0.3*natural, bag)
    return round((110 + 350*state['airway_obstruction_percent']/100)*effort +
                 rng.uniform(-3, 3))


def cpr_proxy(t, state):
    return round(25*_pulse(t, 1.7), 2) if state['compressions_on'] else 0.0


def ecg_trace(t, state, count=160, duration_s=5.0):
    """Decorative educational waveform; cannot drive an actual patient monitor."""
    rhythm = state['rhythm']
    if rhythm == 'asystole':
        return [0.0]*count
    out = []
    for index in range(count):
        x = t-duration_s+(index/(count-1))*duration_s
        if rhythm == 'vf':
            v = 0.42*math.sin(2*math.pi*5.7*x)+0.28*math.sin(2*math.pi*8.1*x+0.9)
        else:
            period = 60/state['heart_rate_bpm']
            phase = (x % period)/period
            # A stylized pulse complex; intentionally NOT a valid ECG model.
            v = (0.09*math.exp(-((phase-0.2)/0.055)**2)
                 -0.22*math.exp(-((phase-0.43)/0.025)**2)
                 +1.15*math.exp(-((phase-0.48)/0.018)**2)
                 -0.27*math.exp(-((phase-0.53)/0.022)**2)
                 +0.22*math.exp(-((phase-0.76)/0.09)**2))
        out.append(round(v, 4))
    return out
