"""Unit tests for the presentation dashboard's parsing and demo-mode API."""
import sys
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pressure_presentation_ui import (  # noqa: E402
    SerialPressureReader,
    SimulatedPressureReader,
    create_app,
    find_sensorhub_port,
)


class PressurePresentationTests(unittest.TestCase):
    def test_valid_pressure_sample(self):
        reader = SerialPressureReader("UNUSED")
        reader.handle_line("1000,2600,2500,100,IDLE,2,1,1")
        state = reader.snapshot()
        self.assertEqual(state["delta"], 100)
        self.assertEqual(state["baseline"], 2500)
        self.assertEqual(state["candidate_count"], 2)
        self.assertEqual(state["firmware_state"], "IDLE")
        self.assertTrue(state["data_fresh"])

    def test_invalid_calibration_no_fabricated_delta(self):
        reader = SerialPressureReader("UNUSED")
        reader.handle_line("1000,2500,,,CAL_REQUIRED,2,1,0")
        state = reader.snapshot()
        self.assertIsNone(state["delta"])
        self.assertFalse(state["baseline_ok"])

    def test_failed_sample_is_not_shown_as_pressure(self):
        reader = SerialPressureReader("UNUSED")
        reader.handle_line("1000,3000,2500,500,POSITIVE_EVENT,2,1,1")
        reader.handle_line("1200,,2500,,POSITIVE_EVENT,2,0,1")
        state = reader.snapshot()
        self.assertIsNone(state["raw"])
        self.assertIsNone(state["delta"])
        self.assertFalse(state["sample_ok"])

    def test_event_comments(self):
        reader = SerialPressureReader("UNUSED")
        reader.handle_line("# CANDIDATE_VENTILATION count=3, peak_delta_raw=1520, duration_ms=900")
        reader.handle_line("# NEGATIVE_PRESSURE_END min_delta_raw=-305, duration_ms=800")
        state = reader.snapshot()
        self.assertEqual(state["last_positive_peak"], 1520)
        self.assertEqual(state["last_negative_peak"], 305)

    def test_simulated_mode_is_explicit(self):
        reader = SimulatedPressureReader()
        snapshot = reader.snapshot()
        self.assertTrue(snapshot["demo_mode"])
        self.assertEqual(snapshot["port"], "SIMULATED")
        self.assertTrue(snapshot["data_fresh"])
        self.assertFalse(reader.recalibrate())

    def test_demo_api_and_calibration_disabled(self):
        app = create_app(SimulatedPressureReader())
        client = app.test_client()
        self.assertEqual(client.get("/").status_code, 200)
        response = client.get("/api/state")
        self.assertTrue(response.json["demo_mode"])
        self.assertEqual(client.post("/api/recalibrate").status_code, 503)

    def test_local_stop_requires_same_origin(self):
        stopped = threading.Event()
        app = create_app(SimulatedPressureReader(), stop_callback=stopped.set)
        client = app.test_client()

        denied = client.post("/api/stop", headers={"Origin": "https://other.example"})
        self.assertEqual(denied.status_code, 403)
        self.assertFalse(stopped.is_set())

        accepted = client.post("/api/stop", headers={"Origin": "http://localhost"})
        self.assertEqual(accepted.status_code, 200)
        self.assertTrue(stopped.wait(2))

    def test_sensorhub_auto_detection(self):
        ports = [
            SimpleNamespace(device="COM5", vid=None, pid=None),
            SimpleNamespace(device="COM8", vid=0x239A, pid=0x001B),
            SimpleNamespace(device="COM3", vid=0x239A, pid=0x801B),
        ]
        with patch("pressure_presentation_ui.list_ports.comports", return_value=ports):
            self.assertEqual(find_sensorhub_port(), "COM3")


if __name__ == "__main__":
    unittest.main()
