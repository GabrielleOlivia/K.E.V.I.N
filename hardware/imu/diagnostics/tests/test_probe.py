import unittest
from tools.parse_probe import summarize


class ProbeParserTests(unittest.TestCase):
    def test_reports_device_found(self):
        log = '# B BHI candidate 0x28 ACK FUSER2_ID=0x89 BHI360_IDENTIFIED REV=0x02 BOOT_STATUS=0x01\n'
        self.assertIn('BHI360_IDENTIFIED', summarize(log)['B:0x28'])

    def test_no_ack_not_a_device(self):
        self.assertEqual(summarize('# A BHI candidate 0x29 NO_ACK\n'), {'A:0x29': 'NO_ACK'})

    def test_uses_last_observation(self):
        log = '# B BHI candidate 0x28 ACK FUSER2_ID=0x89 BHI360_IDENTIFIED\n# B BHI candidate 0x28 NO_ACK\n'
        self.assertEqual(summarize(log)['B:0x28'], 'NO_ACK')

    def test_ignores_unrelated_lines(self):
        self.assertEqual(summarize('# A pressure ADC 0x68 ACK\n# PROBE_BEGIN t_ms=1000\n'), {})


if __name__ == '__main__':
    unittest.main()
