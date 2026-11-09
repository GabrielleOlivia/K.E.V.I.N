"""Review-driven edge cases, transport semantics and supplied examples."""
import importlib.util
import os
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path
from kevin.protocol import decode, ProtocolError
from kevin.service import IntegrationService
from kevin.transports.serial_source import SerialSource
from kevin.simulation.engine import Simulator
from tests.support import *

class ReviewTests(unittest.TestCase):
    def test_physical_cannot_claim_simulation_calibration(self):
        c,m=setup_manager()
        for i,cal in enumerate(('simulated','not_required'),1):
            m.accept(replace(sample(seq=i,t=i*100),calibration=cal),'wire')
            self.assertEqual(m.snapshot()['channels']['pressure']['state'],'invalid')
    def test_baseline_not_accepted_for_imu(self):
        m=SensorManager(load_registry());m.accept(hello(node='head_node'),'wire')
        m.accept(replace(sample(node='head_node',sensor='head_imu',value=[1,0,0,0]),calibration='baseline'),'wire')
        self.assertFalse(m.snapshot()['channels']['head_imu']['valid'])
    def test_mapping_expires_without_new_sample(self):
        c=Clock();m=SensorManager(load_registry(),c);sim=Simulator(IntegrationService(m),load_registry());sim.step()
        m.install_time_mapping('head_node',sim.sessions['head_node'],100,0,.1)
        c.advance(.05);sim.step();c.advance(.06)
        self.assertFalse(m.snapshot()['derived']['relative_rotation_deg']['valid'])
    def test_fault_recovery_does_not_revive_stale_sample(self):
        c,m=setup_manager();m.accept(sample(),'wire');c.advance(2)
        m.accept(Message(1,'status','pressure_node','a',2,2100),'wire')
        self.assertEqual(m.snapshot()['channels']['pressure']['state'],'stale')
    def test_mutating_snapshot_events_is_harmless(self):
        c,m=setup_manager();s=m.snapshot();s['events'][0]['detail']='changed'
        self.assertNotEqual(m.snapshot()['events'][0]['detail'],'changed')
    def test_huge_numeric_json_is_protocol_error(self):
        import json
        d=sample().to_dict();d['value']=10**500
        with self.assertRaises(ProtocolError):decode(json.dumps(d))
    def test_supplied_native_example(self):
        m=SensorManager(load_registry())
        path=Path(__file__).resolve().parents[1]/'examples/protocol.jsonl'
        for line in path.read_bytes().splitlines():self.assertTrue(m.accept(decode(line),'example'))
    def test_example_session_handshake_on_boot_request(self):
        c=Clock();m=SensorManager(load_registry(),c);service=IntegrationService(m);stop=threading.Event();written=[]
        class Port:
            sent=False
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def write(self,data):written.append(data);return len(data)
            def read(self,n):
                if not self.sent:self.sent=True;return b'# SESSION_REQUIRED\n'
                stop.set();return b''
        worker=SerialSource(service,'fake','head',stop=stop,serial_factory=lambda *a,**k:Port(),session_handshake=True)
        worker.start();worker.join(2)
        self.assertEqual(len(written),2);self.assertTrue(all(w.startswith(b'SESSION ') for w in written))
        self.assertNotEqual(written[0],written[1]);self.assertNotIn('parse_error',m.snapshot()['diagnostics'])

@unittest.skipUnless(os.name=='posix' and importlib.util.find_spec('serial'), 'POSIX PTY and optional pyserial required')
class PtySerialTests(unittest.TestCase):
    def test_real_pyserial_read_and_unplug_on_virtual_port(self):
        import pty
        import serial
        master,slave=pty.openpty();port=os.ttyname(slave)
        c=Clock();m=SensorManager(load_registry(),c);service=IntegrationService(m);stop=threading.Event();opened=threading.Event()
        def factory(*a,**k):
            result=serial.Serial(*a,**k);opened.set();return result
        worker=SerialSource(service,port,'serial:pressure',mode='pressure',stop=stop,serial_factory=factory,reconnect_s=.02)
        try:
            worker.start();self.assertTrue(opened.wait(2))
            os.write(master,b'100,2542,2540,');os.write(master,b'2,IDLE,0,1,1\n')
            deadline=time.monotonic()+2
            while m.snapshot()['channels']['pressure']['state']!='active' and time.monotonic()<deadline:stop.wait(.01)
            self.assertEqual(m.snapshot()['channels']['pressure']['value'],2)
            os.close(master);master=None
            deadline=time.monotonic()+2
            while m.snapshot()['channels']['pressure']['state']!='disconnected' and time.monotonic()<deadline:stop.wait(.01)
            self.assertEqual(m.snapshot()['channels']['pressure']['state'],'disconnected')
        finally:
            stop.set();worker.join(2)
            if master is not None:os.close(master)
            os.close(slave)
