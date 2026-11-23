"""Four-sensor bench integration tests. No physical COM / hardware implied."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dual_imu import TiltPair, accelerometer_tilt
from engine import PatientEngine, Settings, PressureBreathDetector, ToFCompressionDetector
from serial_bridge import parse_line


class DualImuTests(unittest.TestCase):
    def test_four_serial_inputs(self):
        self.assertEqual(parse_line("# accel,t_ms=42,sensor=head,x_raw=100,y_raw=20,z_raw=3995,valid=1").kind, "head_accel")
        self.assertEqual(parse_line("# accel,t_ms=42,sensor=chest,x_raw=0,y_raw=0,z_raw=4096,valid=1").value,
                         (0.0, 0.0, 4096.0))
        self.assertEqual(parse_line("# pressure,t_ms=42,raw_adc=1221,valid=1").kind, "pressure")
        self.assertEqual(parse_line("# tof,t_ms=42,raw_mm=32,err=0,valid=1").kind, "tof")

    def test_invalid_acceleration_never_becomes_valid(self):
        for line in (
            "# accel,sensor=head,x_raw=1,y_raw=2,z_raw=3,valid=0",
            "# accel,sensor=head,x_raw=nan,y_raw=2,z_raw=3,valid=1",
            "# accel,sensor=other,x_raw=1,y_raw=2,z_raw=3,valid=1",
            "# accel,sensor=head,x_raw=1,y_raw=2,valid=1",
        ):
            self.assertIsNone(parse_line(line))

    def test_gravity_tilt_is_not_clinical_head_angle(self):
        self.assertAlmostEqual(accelerometer_tilt((0, 0, 4096), "pitch"), 0)
        self.assertLess(accelerometer_tilt((2048, 0, 3547), "pitch"), -20)

    def test_zero_requires_both_imus(self):
        pair = TiltPair()
        pair.update("head", (0, 0, 4096), 0.1)
        self.assertFalse(pair.zero(0.2))
        self.assertIsNone(pair.relative(0.2))
        pair.update("chest", (0, 0, 4096), 0.2)
        self.assertTrue(pair.zero(0.3))
        self.assertAlmostEqual(pair.relative(0.3), 0.0)

    def test_same_body_rotation_cancels_in_relative_angle(self):
        pair = TiltPair()
        for role in ("head", "chest"):
            pair.update(role, (0, 0, 4096), 1.0)
        self.assertTrue(pair.zero(1.0))
        for role in ("head", "chest"):
            pair.update(role, (2048, 0, 3547), 1.1)
        self.assertAlmostEqual(pair.relative(1.1), 0.0, places=2)

    def test_head_flexion_changes_relative_angle(self):
        pair = TiltPair()
        pair.update("head", (0, 0, 4096), 1.0)
        pair.update("chest", (0, 0, 4096), 1.0)
        self.assertTrue(pair.zero(1.0))
        pair.update("head", (2048, 0, 3547), 1.1)
        angle = pair.relative(1.1)
        self.assertLess(angle, -25.0)
        self.assertGreater(angle, -35.0)

    def test_missing_stale_and_mount_changes_block_valid_angle(self):
        pair = TiltPair()
        pair.update("head", (0, 0, 4096), 1.0)
        pair.update("chest", (0, 0, 4096), 1.0)
        self.assertTrue(pair.zero(1.1))
        self.assertIsNone(pair.relative(3.1))  # older than 2s
        self.assertIsNone(pair.relative(1.2, head_axis="roll"))  # needs re-zero
        pair.discard("chest")
        self.assertIsNone(pair.relative(1.2))

    def test_pressure_tof_imu_all_feed_toy_model(self):
        pair = TiltPair()
        pressure = PressureBreathDetector()
        tof = ToFCompressionDetector()
        model = PatientEngine()
        pair.update("head", (0, 0, 4096), 0)
        pair.update("chest", (0, 0, 4096), 0)
        self.assertTrue(pair.zero(0))
        for i in range(8):
            pressure.feed(1500)
            tof.feed(50, i * 0.1)
        self.assertTrue(pressure.feed(1900))
        model.breath()
        self.assertTrue(tof.feed(37, 1.0))
        model.compression()
        pair.update("head", (2200, 0, 3436), 1.0)
        pair.update("chest", (0, 0, 4096), 1.0)
        angle = pair.relative(1.0)
        model.step(.1, Settings(mode="reactive", pressure_valid=True,
                                head_valid=True, chest_valid=True,
                                head_pitch_deg=angle))
        self.assertLess(model.airway, 0.7)
        self.assertGreater(model.sample_wave("cpr"), 0.5)

    def test_missing_chest_holds_physio(self):
        model = PatientEngine()
        for _ in range(100):
            model.step(.1, Settings(mode="reactive", pressure_valid=True,
                                    head_valid=True, chest_valid=False))
        self.assertEqual(model.spo2, 98)
        self.assertIn("CHEST IMU", model.status)


if __name__ == "__main__":
    unittest.main()
