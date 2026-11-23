"""K.E.V.I.N. infant manikin training simulation (illustrative, NOT clinical).

No real-time/medical claims: rates, angle bands, delays, CPR displacement
thresholds and vital-sign curves are intentionally adjustable toy-model choices.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from math import exp
from statistics import median


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass
class Settings:
    mode: str = "default"         # 'default' or 'reactive'
    source: str = "virtual"       # 'virtual' or 'serial'
    scenario: str = "Normal"      # Normal, Apnoea, Choking, Cardiac arrest
    head_pitch_deg: float = 0.0   # neutral-referenced head minus chest tilt
    pressure_valid: bool = True  # False = sensor unavailable; NOT apnoea
    tof_valid: bool = True
    head_valid: bool = True  # False = head IMU stale or uncalibrated
    chest_valid: bool = True  # False = chest IMU stale or uncalibrated
    speed: float = 1.0


class PressureBreathDetector:
    """Detect *pressure pulses*, not physical airflow (requires calibration)."""

    def __init__(self, threshold: int = 180):
        self.threshold = threshold
        self.baseline: float | None = None
        self.samples: deque[float] = deque(maxlen=12)
        self.latched = False
        self.latest: int | None = None
        self.ready = False

    def reset(self):
        self.__init__(self.threshold)

    def feed(self, raw: int) -> bool:
        self.latest = raw
        if self.baseline is None:
            self.samples.append(float(raw))
            if len(self.samples) >= 8:
                self.baseline = median(self.samples)
                self.ready = True
            return False
        # On the tested module the ADC increases for an applied breath pulse.
        # Do not treat negative-going suction as delivered positive pressure.
        amplitude = raw - self.baseline
        if amplitude < self.threshold * 0.35:
            self.baseline = self.baseline * 0.997 + raw * 0.003
        if not self.latched and amplitude >= self.threshold:
            self.latched = True
            return True
        if self.latched and amplitude <= self.threshold * 0.45:
            self.latched = False
        return False


class ToFCompressionDetector:
    """Detect relative ToF changes; NOT clinical chest compression depth."""

    def __init__(self, threshold_mm: float = 8.0, polarity: str = "closer"):
        self.threshold_mm = threshold_mm
        self.polarity = polarity
        self.baseline_mm: float | None = None
        self.samples: deque[float] = deque(maxlen=8)
        self.latest_mm: float | None = None
        self.latched = False
        self.last_event = -100.0

    def reset(self):
        threshold, polarity = self.threshold_mm, self.polarity
        self.__init__(threshold, polarity)

    def calibrate(self):
        self.baseline_mm = self.latest_mm
        self.samples.clear()
        self.latched = False

    def feed(self, mm: float, timestamp: float) -> bool:
        self.latest_mm = mm
        if self.baseline_mm is None:
            self.samples.append(mm)
            if len(self.samples) >= 6:
                self.baseline_mm = median(self.samples)
            return False
        displacement = (self.baseline_mm - mm if self.polarity == "closer"
                        else mm - self.baseline_mm)
        if displacement <= self.threshold_mm * 0.2 and not self.latched:
            self.baseline_mm = self.baseline_mm * 0.995 + mm * 0.005
        if not self.latched and displacement >= self.threshold_mm:
            self.latched = True
            if timestamp - self.last_event > 0.27:
                self.last_event = timestamp
                return True
        if self.latched and displacement <= self.threshold_mm * 0.4:
            self.latched = False
        return False


class PatientEngine:
    """Directional physiology teaching toy driven by two relative IMU tilts."""

    NO_BREATH_SECONDS = 4.5     # DEMO timeout, not an infant diagnostic cut-off

    def __init__(self):
        self.reset()

    def reset(self):
        self.time = 0.0
        self.hr = 138.0
        self.spo2 = 98.0
        self.resp_rate = 36.0
        self.etco2 = 35.0
        self.sbp = 76.0
        self.dbp = 43.0
        self.perfusion = 1.0
        self.airway = 1.0
        self.arrest = False
        self.crit_time = 0.0
        self.rosctime = 0.0
        self.last_breath = -1e6
        self.last_good_breath = -1e6
        self.last_auto_breath = -1e6
        self.breath_times: deque[float] = deque(maxlen=90)
        self.cpr_times: deque[float] = deque(maxlen=250)
        self.status = "STABLE"
        self.ventilating = True
        self.head_pitch = 0.0
        self.wave_phase = 0.0
        self.last_event = "Ready"

    def breath(self):
        self.last_breath = self.time
        self.breath_times.append(self.time)
        self.last_event = "Pressure pulse received"

    def compression(self):
        if self.cpr_times and self.time - self.cpr_times[-1] < 0.27:
            return
        self.cpr_times.append(self.time)
        self.last_event = "ToF displacement / compression detected"

    def _airway_fraction(self, angle: float) -> float:
        # Demonstration bands only. No universal medically valid degree cutoff.
        if angle < -15:
            return clamp(1 - (abs(angle) - 15) / 36, 0.05, 1)
        if angle > 30:
            return clamp(1 - (angle - 30) / 30, 0.10, 1)
        return 1.0

    def _rate(self, events: deque[float], max_age: float) -> float:
        recent = [x for x in events if self.time - x <= max_age]
        if len(recent) < 2:
            return 0.0
        intervals = [b - a for a, b in zip(recent, recent[1:]) if 0.2 < b - a < 10]
        return clamp(60 / median(intervals), 0, 240) if intervals else 0.0

    def _smooth(self, value: float, target: float, dt: float, rate: float) -> float:
        return value + clamp(target - value, -rate * dt, rate * dt)

    def step(self, dt: float, settings: Settings):
        dt = clamp(dt, 0, 0.3) * clamp(settings.speed, 0.2, 8)
        self.time += dt
        if settings.mode == "reactive" and (not settings.head_valid or not settings.chest_valid):
            self.status = "HEAD IMU / CHEST IMU SIGNAL UNAVAILABLE • physiology held"
            self.ventilating = False
            return
        self.head_pitch = settings.head_pitch_deg if settings.mode == "reactive" else 0.0
        self.airway = self._airway_fraction(self.head_pitch)
        if settings.scenario == "Choking":
            self.airway = min(self.airway, 0.07)

        if settings.mode == "default":
            # Independent of all sensors; default stable, scenarios can be selected.
            if settings.scenario != "Apnoea" and self.time - self.last_auto_breath >= 60 / 36:
                self.breath()
                self.last_auto_breath = self.time
            breathing = settings.scenario not in ("Apnoea", "Cardiac arrest")
            self.resp_rate = 36 if breathing else 0
            self.airway = 0.07 if settings.scenario == "Choking" else 1.0
        else:
            if not settings.pressure_valid:
                self.status = "PRESSURE SIGNAL UNAVAILABLE • physiology held"
                self.ventilating = False
                return  # No data must never be interpreted as no breathing
            breathing = (self.time - self.last_breath <= self.NO_BREATH_SECONDS
                         and settings.scenario != "Apnoea")
            self.resp_rate = self._rate(self.breath_times, 15) if breathing else 0
        self.ventilating = breathing

        effective = breathing and self.airway >= 0.55
        if effective:
            self.last_good_breath = self.time
        # Toy model: directional effects only; not published rate constants.
        if effective:
            oxygen_target = 98.0
            spo2_rate = 0.44 if self.spo2 < oxygen_target else 0.16
        elif breathing and self.airway > 0.2:
            oxygen_target = 64.0
            spo2_rate = 0.28
        else:
            oxygen_target = 38.0
            spo2_rate = 0.63
        self.spo2 = self._smooth(self.spo2, oxygen_target, dt, spo2_rate)

        cpr_rate = self._rate(self.cpr_times, 10)
        active_cpr = bool(self.cpr_times and self.time - self.cpr_times[-1] <= 2.0)
        cpr_factor = clamp(cpr_rate / 110, 0, 1) if active_cpr else 0

        if settings.scenario == "Cardiac arrest":
            self.arrest = True
        if self.spo2 < 53 and not effective:
            self.crit_time += dt
        else:
            self.crit_time = max(0, self.crit_time - 2 * dt)
        if self.crit_time >= 16:
            self.arrest = True

        if self.arrest:
            # CPR creates some simulated perfusion, but not spontaneous pulse/ROSC.
            self.hr = self._smooth(self.hr, 0, dt, 20)
            self.perfusion = cpr_factor * 0.32
            self.sbp = self._smooth(self.sbp, cpr_factor * 35, dt, 20)
            self.dbp = self._smooth(self.dbp, cpr_factor * 16, dt, 12)
            self.status = "CARDIAC ARREST • CPR does not imply ROSC"
        else:
            if self.spo2 > 94:
                target_hr = 138
            elif self.spo2 > 85:
                target_hr = 154
            elif self.spo2 > 60:
                target_hr = 55 + (self.spo2 - 60) * 3.96
            else:
                target_hr = 40
            self.hr = self._smooth(self.hr, target_hr, dt, 3.6)
            self.perfusion = clamp((self.hr / 135) * (self.spo2 / 97), 0.2, 1)
            self.sbp = self._smooth(self.sbp, 76 * self.perfusion, dt, 3)
            self.dbp = self._smooth(self.dbp, 43 * self.perfusion, dt, 2)
            if self.hr < 95:
                self.status = "BRADYCARDIA • simulated deterioration"
            elif self.spo2 < 92:
                self.status = "HYPOXAEMIA • simulated deterioration"
            elif breathing and self.airway < 0.55:
                self.status = "AIRWAY OBSTRUCTION • pressure ≠ effective air"
            elif not breathing:
                self.status = "NO RECENT PRESSURE BREATHS • simulated apnoea"
            else:
                self.status = "STABLE"
        self.etco2 = 0 if (not breathing or self.arrest) else 35 * self.airway * max(0.3, self.perfusion)
        self.wave_phase = (self.wave_phase + dt * max(0, self.hr) / 60) % 1

    def display(self) -> dict:
        cpr_rate = self._rate(self.cpr_times, 10)
        return {
            "hr": round(self.hr),
            "spo2": None if self.arrest else round(self.spo2),
            "rr": round(self.resp_rate),
            "etco2": None if not self.ventilating or self.arrest else round(self.etco2),
            "bp": f"{round(self.sbp)}/{round(self.dbp)}" if not self.arrest else "--/--",
            "airway": self.airway,
            "cpr_rate": round(cpr_rate) if self.cpr_times and self.time - self.cpr_times[-1] <= 3 else 0,
            "status": self.status,
            "arrest": self.arrest,
        }

    def sample_wave(self, name: str) -> float:
        """Dimensionless illustrative monitor traces, never measured ECG/SpO2."""
        phase = self.wave_phase
        age_cpr = self.time - self.cpr_times[-1] if self.cpr_times else 1e6
        # CPR changes the tracing through *synthetic compression artefact*,
        # not a restored intrinsic heartbeat.
        compression_artifact = (0.35 * exp(-((age_cpr - 0.055) / 0.03) ** 2)
                                if age_cpr < 0.24 else 0.0)
        if name == "ecg":
            if self.arrest and self.hr < 8:
                return compression_artifact
            return compression_artifact + (0.13 * exp(-((phase - 0.20) / 0.055) ** 2)
                    - 0.16 * exp(-((phase - 0.39) / 0.018) ** 2)
                    + 1.05 * exp(-((phase - 0.42) / 0.011) ** 2)
                    - 0.25 * exp(-((phase - 0.46) / 0.022) ** 2)
                    + 0.26 * exp(-((phase - 0.70) / 0.1) ** 2))
        if name == "pleth":
            if self.arrest:
                return (self.perfusion * 1.4 * exp(-((age_cpr - 0.16) / 0.13) ** 2)
                        if age_cpr < 0.5 else 0.0)
            p = (phase - 0.15) % 1
            return max(0.0, p * exp(-5.7 * p) * 14) * self.perfusion
        if name == "resp":
            age = self.time - self.last_breath
            if age < 0 or age > 2.0 or not self.ventilating:
                return 0.0
            return (1 - exp(-max(0.0, age) * 4)) * exp(-1.45 * max(0, age)) * self.airway
        if name == "cpr":
            # Short synthetic pulse drawn only after a real/virtual ToF event.
            return (exp(-((age_cpr - 0.05) / 0.07) ** 2) if 0 <= age_cpr < 0.4 else 0.0)
        return 0.0
