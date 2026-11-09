from pathlib import Path
import unittest
from kevin.adapters.pressure_csv import PressureCSV, COLUMNS
from kevin.protocol import ProtocolError, encode, decode
from kevin.manager import SensorManager
from kevin.registry import load_registry

ROOT=Path(__file__).resolve().parents[1]
class PressureTests(unittest.TestCase):
    def test_comments_header_and_valid_row(self):
        d=PressureCSV();self.assertEqual(d.feed(COLUMNS),[]);self.assertEqual(d.feed('# READY'),[])
        self.assertEqual(d.diagnostic,'# READY')
        h,m=d.feed('5100,2542,2540,2,IDLE,0,1,1')
        self.assertEqual(h.type,'hello');self.assertEqual(m.value,2);self.assertEqual(m.unit,'adc_count')
        self.assertEqual(m.meta['candidate_count'],0);self.assertFalse(m.meta['pressure_calibrated'])
        self.assertEqual(decode(encode(m)),m)

    def test_failure_and_calibrating(self):
        d=PressureCSV();h,m=d.feed('100,,,,CAL_REQUIRED,3,0,0')
        self.assertIsNone(m.value);self.assertFalse(m.valid);self.assertEqual(m.error,'ADC_READ_FAILED')
        m=d.feed('200,2540,,,CALIBRATING,3,1,0')[0]
        self.assertEqual(m.calibration,'calibrating');self.assertIsNone(m.value)

    def test_bad_rows(self):
        for row in ('1,2,3','1,2,1,9,IDLE,0,1,1','1,2,1,1,IDLE,0,2,1',
                    '1,,1,,IDLE,0,1,1','-1,2,1,1,IDLE,0,1,1',
                    '1,40000,1,39999,IDLE,0,1,1','1,2,,,POSITIVE_EVENT,0,1,0',
                    '1,,,,CAL_REQUIRED,-1,0,0'):
            with self.subTest(row=row),self.assertRaises(ProtocolError): PressureCSV().feed(row)

    def test_reboot_header_and_regression(self):
        d=PressureCSV();a=d.feed('9000,3,2,1,IDLE,0,1,1')[0].boot_id
        d.feed(COLUMNS);b=d.feed('100,3,2,1,IDLE,0,1,1')[0].boot_id
        self.assertNotEqual(a,b)
        c=d.feed('50,3,2,1,IDLE,0,1,1')[0].boot_id;self.assertNotEqual(b,c)

    def test_duplicate_and_rollover(self):
        d=PressureCSV();a=d.feed('4294967290,3,2,1,IDLE,0,1,1')[0].boot_id
        row=d.feed('4,3,2,1,IDLE,0,1,1');self.assertEqual(len(row),1);self.assertEqual(row[0].boot_id,a)
        with self.assertRaises(ProtocolError):d.feed('4,3,2,1,IDLE,0,1,1')

    def test_actual_repository_log(self):
        # Existing bench artifact, not newly performed hardware testing.
        path=ROOT/'firmware/pressure_legacy/data/pressure_20260922_145124.txt'
        d=PressureCSV();rows=0
        for line in path.read_bytes().splitlines():
            if not line or line.startswith(b'---'):continue
            messages=d.feed(line)
            for m in messages:decode(encode(m))
            rows+=sum(m.type=='measurement' for m in messages)
        self.assertGreater(rows,200)
