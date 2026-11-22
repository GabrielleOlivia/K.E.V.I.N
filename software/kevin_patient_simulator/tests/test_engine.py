import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import PatientEngine, Settings, PressureBreathDetector, ToFCompressionDetector
from serial_bridge import parse_line


class EngineTests(unittest.TestCase):
    def test_default_ignores_head_and_sensor_state(self):
        a, b = PatientEngine(), PatientEngine()
        for _ in range(200):
            a.step(.1, Settings(mode="default", head_pitch_deg=-60, pressure_valid=False))
            b.step(.1, Settings(mode="default", head_pitch_deg=60, pressure_valid=True))
        self.assertEqual(a.display(), b.display())
        self.assertEqual(a.status, "STABLE")

    def test_reactive_apnea_responds_to_missing_pressure_pulses(self):
        e = PatientEngine()
        cfg = Settings(mode="reactive", pressure_valid=True)
        for _ in range(400):
            e.step(.1, cfg)
        self.assertLess(e.spo2, 98)
        self.assertEqual(e.display()["rr"], 0)

    def test_missing_imu_does_not_silently_assume_head_neutral(self):
        e = PatientEngine()
        for _ in range(100):
            e.step(.1, Settings(mode="reactive", pressure_valid=True, head_valid=False))
        self.assertEqual(e.spo2, 98)
        self.assertIn("HEAD IMU", e.status)

    def test_cpr_renders_sensor_event_pulse(self):
        e = PatientEngine()
        e.compression()
        e.step(.05, Settings(mode="reactive"))
        self.assertGreater(e.sample_wave("cpr"), 0.5)

    def test_imu_status_parsing(self):
        self.assertEqual(parse_line("# IMU_READY firmware_booted=1 kernel=123").kind, "imu_status")
        self.assertEqual(parse_line("# imu,head_pitch_deg=-31.5,valid=1,source=bhi360").value, -31.5)
        self.assertIsNone(parse_line("# imu,valid=0,status=waiting_or_stale"))

    def test_sensor_disconnected_is_not_apnea(self):
        e = PatientEngine()
        for _ in range(500):
            e.step(.1, Settings(mode="reactive", pressure_valid=False))
        self.assertEqual(e.spo2, 98)
        self.assertIn("UNAVAILABLE", e.status)

    def test_head_angle_changes_effective_ventilation(self):
        good, bad = PatientEngine(), PatientEngine()
        for t in range(300):
            if t % 18 == 0:
                good.breath()
                bad.breath()
            good.step(.1, Settings(mode="reactive", head_pitch_deg=0))
            bad.step(.1, Settings(mode="reactive", head_pitch_deg=-55))
        self.assertLess(bad.spo2, good.spo2)
        self.assertLess(bad.airway, good.airway)

    def test_pressure_detection_edges(self):
        d = PressureBreathDetector(180)
        for _ in range(9):
            self.assertFalse(d.feed(2500))
        self.assertTrue(d.feed(2900))
        self.assertFalse(d.feed(3200))
        self.assertFalse(d.feed(2500))
        self.assertTrue(d.feed(2800))

    def test_tof_detection(self):
        d = ToFCompressionDetector(8)
        for i in range(8):
            self.assertFalse(d.feed(40, i * .1))
        self.assertTrue(d.feed(28, 1.0))
        self.assertFalse(d.feed(28, 1.1))
        d.feed(40, 1.5)
        self.assertTrue(d.feed(28, 1.8))

    def test_live_pressure_and_tof_events_feed_same_patient(self):
        model = PatientEngine()
        pressure = PressureBreathDetector(180)
        tof = ToFCompressionDetector(8)
        for idx in range(8):
            pressure.feed(2500)
            tof.feed(50, idx * .10)
        # A pressure pulse received while the head is flexed is less effective
        # than the same pulse with a neutral head.
        self.assertTrue(pressure.feed(3200))
        model.breath()
        self.assertTrue(tof.feed(34, 1.0))
        model.compression()
        model.step(0.1, Settings(mode="reactive", head_pitch_deg=-55,
                                  head_valid=True, pressure_valid=True, tof_valid=True))
        self.assertLess(model.airway, .55)
        self.assertGreater(model.sample_wave("cpr"), 0)
        self.assertGreater(model.time, 0)

    def test_negative_pressure_does_not_count_as_delivered_breath(self):
        pressure = PressureBreathDetector(threshold=180)
        for _ in range(9):
            pressure.feed(2500)
        self.assertFalse(pressure.feed(2000))
        pressure.feed(2500)
        self.assertTrue(pressure.feed(2800))

    def test_v1_serial(self):
        p = parse_line("# pressure,t_ms=123,raw_adc=6541,valid=1,pressure_calibrated=0")
        t = parse_line("# tof,t_ms=124,raw_mm=36,err=0,valid=1")
        self.assertEqual((p.kind, p.value), ("pressure", 6541))
        self.assertEqual((t.kind, t.value), ("tof", 36.0))
        self.assertIsNone(parse_line("# tof,t_ms=124,raw_mm=255,err=7,valid=0"))
        self.assertEqual(parse_line("# imu,head_pitch_deg=-19.2,valid=1").value, -19.2)

    def test_cpr_does_not_create_spontaneous_heartbeat(self):
        e = PatientEngine()
        cfg = Settings(mode="default", scenario="Cardiac arrest")
        for i in range(100):
            if i % 5 == 0:
                e.compression()
            e.step(.1, cfg)
        self.assertTrue(e.arrest)
        self.assertEqual(e.display()["spo2"], None)

if __name__ == "__main__":
    unittest.main()

