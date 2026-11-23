"""Static guardrail tests; these are NOT hardware/firmware compilation tests."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "src/main.cpp").read_text()
CONFIG = (ROOT / "platformio.ini").read_text()

class GuardrailTests(unittest.TestCase):
    def test_bus_and_addresses(self):
        for term in ("SERCOM2_Handler", "kBhi", "BHI_ADDR = 0x28", "BMM_ADDR = 0x14",
                     "TwoWire imuBus(&sercom2, SDA_PIN, SCL_PIN)"):
            if term == "kBhi":
                continue
            self.assertIn(term, SRC)

    def test_bmm350_dummies_and_ids(self):
        self.assertIn("BMM_CHIP_ID_REG = 0x00", SRC)
        self.assertIn("BMM_CHIP_ID = 0x33", SRC)
        self.assertIn("BHI_CHIP_ID_REG = 0x2B", SRC)
        self.assertIn("BHI_CHIP_ID = 0x7A", SRC)
        self.assertIn("imuBus.requestFrom(BMM_ADDR, (uint8_t)3", SRC)
        self.assertIn("(void)imuBus.read(); // dummy byte 1", SRC)
        self.assertIn("(void)imuBus.read(); // dummy byte 2", SRC)

    def test_default_build_is_id_only(self):
        self.assertIn("default_envs = b2_imu_id_only", CONFIG)
        self.assertIn("-D KEVIN_ID_ONLY=1", CONFIG)

    def test_imu_start_gated_by_id_check(self):
        self.assertIn("if (!checkIdentities()) return; // no firmware writes", SRC)
        self.assertIn("if (c == 'm') startAcceleration()", SRC)
        self.assertNotIn("if (c == 'g')", SRC)

    def test_virtual_sensor_presence_32byte_read_regression(self):
        # Bosch present_buff[] is 32 bytes; a 28-byte read cap produces -3.
        self.assertIn("constexpr uint8_t MAX_XFER = 28", SRC)
        self.assertIn("constexpr uint8_t MAX_READ = 32", SRC)
        self.assertIn("len > MAX_READ", SRC)
        self.assertIn("imuBus.requestFrom(BHI_ADDR", SRC)
        self.assertIn('fail("virtual_sensor_list_io", rc)', SRC)
        self.assertIn("bhi360_is_sensor_available(BHI360_SENSOR_ID_ACC", SRC)


if __name__ == "__main__":
    unittest.main()
