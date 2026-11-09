import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from kevin.app import replay_pressure
from kevin.service import IntegrationService
from tests.support import *
ROOT=Path(__file__).resolve().parents[1]

class CliTests(unittest.TestCase):
    def test_replay_example_and_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'log.jsonl'
            r=subprocess.run([sys.executable,'-m','kevin','--mode','replay','--pressure-file','examples/pressure.csv','--speed','100','--no-web','--duration','.6','--log',str(path)],cwd=ROOT,capture_output=True,text=True,timeout=6)
            self.assertEqual(r.returncode,0,r.stderr)
            records=[json.loads(l) for l in path.read_text().splitlines()]
            messages=[r['message'] for r in records if r['kind']=='message']
            self.assertTrue(any(not m['valid'] for m in messages if m['type']=='measurement'))
            state=records[-1]['state'];self.assertEqual(state['channels']['pressure']['source'],'replay:pressure')
            self.assertEqual(state['channels']['head_imu']['state'],'missing')
    def test_bad_modes_and_ownership_fail_early(self):
        for args in (['--pressure-port','COM3'],['--mode','physical'],['--disable','typo'],['--duration','nan'],['--jsonl-port','head_node=COM3','--jsonl-port','head_node=COM4']):
            r=subprocess.run([sys.executable,'-m','kevin',*args],cwd=ROOT,capture_output=True,text=True,timeout=3)
            self.assertEqual(r.returncode,2,r.stderr)
    def test_replay_invalid_timestamp_does_not_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'bad.csv'
            path.write_text('100,3,2,1,IDLE,0,1,1\n999999999999999,garbage\n200,4,2,2,IDLE,0,1,1\n')
            c=Clock();m=SensorManager(load_registry(),c);service=IntegrationService(m)
            replay_pressure(service,path,threading.Event(),speed=1000)
            self.assertEqual(m.snapshot()['channels']['pressure']['value'],2)
            self.assertEqual(m.snapshot()['diagnostics']['parse_error'],1)
    def test_replay_long_and_partial_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'bad.csv';path.write_bytes(b'x'*2000+b'\n100,3,2,1,IDLE,0,1,1\n200,4,2,2,IDLE,0,1,1')
            c=Clock();m=SensorManager(load_registry(),c);service=IntegrationService(m)
            replay_pressure(service,path,threading.Event(),100)
            self.assertEqual(m.snapshot()['channels']['pressure']['value'],1)
            self.assertEqual(m.snapshot()['diagnostics']['framing_overflow'],1)
            self.assertEqual(m.snapshot()['diagnostics']['replay_partial_line'],1)
    def test_upstream_byte_preservation(self):
        import hashlib
        root=ROOT/'firmware/pressure_legacy'
        for entry in json.loads((root/'UPSTREAM_MANIFEST.json').read_text())['files']:
            b=(root/entry['path']).read_bytes()
            digest=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
            self.assertEqual(digest,entry['sha'],entry['path'])
