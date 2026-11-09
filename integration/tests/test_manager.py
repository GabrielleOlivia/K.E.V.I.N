import concurrent.futures
from dataclasses import replace
import unittest
from kevin.protocol import Message
from kevin.manager import SensorManager
from kevin.registry import load_registry, SensorSpec
from tests.support import *

class ManagerTests(unittest.TestCase):
    def test_missing_not_zero(self):
        m=SensorManager(load_registry())
        for c in m.snapshot()['channels'].values():
            self.assertIsNone(c['value']);self.assertFalse(c['valid']);self.assertEqual(c['state'],'missing')

    def test_requires_hello_and_registry(self):
        m=SensorManager(load_registry())
        self.assertFalse(m.accept(sample(),'wire'))
        self.assertFalse(m.accept(hello(node='unknown'),'wire'))

    def test_active_stale_disconnected_recovery(self):
        c,m=setup_manager();self.assertTrue(m.accept(sample(),'wire'))
        self.assertEqual(m.snapshot()['channels']['pressure']['state'],'active')
        c.advance(1.0);self.assertEqual(m.snapshot()['channels']['pressure']['state'],'stale')
        c.advance(4.0);self.assertEqual(m.snapshot()['channels']['pressure']['state'],'disconnected')
        self.assertTrue(m.accept(sample(seq=2,t=5100),'wire'))
        self.assertEqual(m.snapshot()['channels']['pressure']['value'],42)

    def test_heartbeat_never_refreshes_measurement(self):
        c,m=setup_manager();m.accept(sample(),'wire');c.advance(2)
        m.accept(Message(1,'heartbeat','pressure_node','a',2,2100),'wire')
        s=m.snapshot()['channels']['pressure'];self.assertEqual(s['state'],'stale');self.assertIsNone(s['value'])

    def test_fault_and_explicit_recovery(self):
        c,m=setup_manager();m.accept(sample(),'wire')
        m.accept(Message(1,'fault','pressure_node','a',2,200,status='fault',error='BUS'),'wire')
        m.accept(Message(1,'heartbeat','pressure_node','a',3,300),'wire')
        self.assertEqual(m.snapshot()['channels']['pressure']['state'],'faulty')
        m.accept(Message(1,'status','pressure_node','a',4,400),'wire')
        self.assertEqual(m.snapshot()['channels']['pressure']['state'],'active')

    def test_invalid_sample_overrides_old_good(self):
        c,m=setup_manager();m.accept(sample(),'wire')
        m.accept(replace(sample(seq=2,t=200),value=None,valid=False,status='invalid',error='READ'),'wire')
        s=m.snapshot()['channels']['pressure'];self.assertEqual(s['state'],'invalid');self.assertIsNone(s['value'])

    def test_calibration_required(self):
        c,m=setup_manager();m.accept(replace(sample(),calibration='uncalibrated'),'wire')
        self.assertEqual(m.snapshot()['channels']['pressure']['state'],'invalid')

    def test_duplicate_out_of_order_do_not_refresh(self):
        c,m=setup_manager();m.accept(sample(seq=2,t=200),'wire');c.advance(1.1)
        self.assertFalse(m.accept(sample(seq=2,t=200),'wire'))
        self.assertFalse(m.accept(sample(seq=1,t=100),'wire'))
        self.assertEqual(m.snapshot()['channels']['pressure']['state'],'stale')

    def test_new_sequence_frozen_acquisition_rejected(self):
        c,m=setup_manager();m.accept(sample(),'wire')
        self.assertFalse(m.accept(sample(seq=2,t=100),'wire'))

    def test_restart_clears_data_retires_boot(self):
        c,m=setup_manager();m.accept(sample(),'wire')
        self.assertFalse(m.accept(sample(boot='b'),'wire'))
        self.assertTrue(m.accept(hello(boot='b'),'wire'))
        self.assertIsNone(m.snapshot()['channels']['pressure']['value'])
        self.assertTrue(m.accept(sample(boot='b'),'wire'))
        self.assertFalse(m.accept(hello(boot='a',seq=3,t=200),'wire'))
        self.assertFalse(m.accept(sample(boot='a',seq=4,t=300),'wire'))

    def test_sequence_wrap(self):
        c,m=setup_manager();m=SensorManager(load_registry(),c)
        m.accept(hello(seq=0xFFFFFFFE),'wire')
        self.assertTrue(m.accept(sample(seq=0xFFFFFFFF),'wire'))
        self.assertTrue(m.accept(sample(seq=0,t=200),'wire'))

    def test_timestamp_wrap_and_regression(self):
        c=Clock();m=SensorManager(load_registry(),c)
        m.accept(hello(t=0xFFFFFF00),'wire')
        self.assertTrue(m.accept(sample(t=0xFFFFFFF0),'wire'))
        c.advance(0.032)
        self.assertTrue(m.accept(sample(seq=2,t=0x10),'wire'))
        self.assertGreater(m.snapshot()['channels']['pressure']['timing']['uptime_ms'],2**32)
        self.assertFalse(m.accept(sample(seq=3,t=0),'wire'))

    def test_delayed_packet_keeps_stale_even_at_reception(self):
        c,m=setup_manager();m.accept(sample(),'wire');c.advance(3)
        self.assertTrue(m.accept(sample(seq=2,t=200),'wire'))
        self.assertEqual(m.snapshot()['channels']['pressure']['state'],'stale')

    def test_bound_source_and_unit(self):
        m=SensorManager(load_registry(),expected_sources={'pressure_node':'port-a'})
        self.assertFalse(m.accept(hello(),'port-b'));self.assertTrue(m.accept(hello(),'port-a'))
        self.assertFalse(m.accept(sample(),'port-b'))
        self.assertFalse(m.accept(replace(sample(),unit='kPa'),'port-a'))

    def test_explicit_disconnect_immediate(self):
        c,m=setup_manager();m.accept(sample(),'wire');m.transport_lost('wire','unplug')
        self.assertEqual(m.snapshot()['channels']['pressure']['state'],'disconnected')
        self.assertTrue(m.accept(sample(seq=2,t=200),'wire'))
        self.assertEqual(m.snapshot()['channels']['pressure']['state'],'active')

    def test_snapshot_isolation(self):
        c,m=setup_manager();m.accept(sample(meta={'x':1}),'wire')
        s=m.snapshot();s['channels']['pressure']['meta']['x']=5
        self.assertEqual(m.snapshot()['channels']['pressure']['meta']['x'],1)

    def test_concurrent_sensor_updates(self):
        specs=[SensorSpec('s'+str(i),'n'+str(i),'value','N',calibration_required=False) for i in range(8)]
        m=SensorManager(specs)
        def worker(i):
            node='n'+str(i);sid='s'+str(i);self.assertTrue(m.accept(hello(node=node),'p'+node))
            for j in range(1,101):
                self.assertTrue(m.accept(Message(1,'measurement',node,'a',j,j,sensor_id=sid,measurement='value',unit='N',value=j,valid=True),'p'+node))
                m.snapshot()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool: list(pool.map(worker,range(8)))
        self.assertEqual(m.snapshot()['diagnostics']['accepted'],808)
        self.assertTrue(all(c['value']==100 for c in m.snapshot()['channels'].values()))

    def test_one_node_multiple_sensors(self):
        specs=[SensorSpec('a','node','force','N'),SensorSpec('b','node','force','N')]
        m=SensorManager(specs);m.accept(hello(node='node'),'wire')
        for seq,sid in enumerate(('a','b'),1):
            self.assertTrue(m.accept(Message(1,'measurement','node','a',seq,100,sensor_id=sid,measurement='force',unit='N',value=1,valid=True,calibration='calibrated'),'wire'))
        self.assertTrue(all(c['valid'] for c in m.snapshot()['channels'].values()))

    def test_mapping_future_and_expiration(self):
        c,m=setup_manager();m.install_time_mapping('pressure_node','a',100,0,1)
        self.assertFalse(m.accept(sample(t=500),'wire'))
        c.advance(0.1);self.assertTrue(m.accept(sample(t=100),'wire'))
        self.assertEqual(m.snapshot()['channels']['pressure']['timing']['quality'],'mapped')
        c.advance(1);self.assertTrue(m.accept(sample(seq=2,t=1100),'wire'))
        self.assertEqual(m.snapshot()['channels']['pressure']['timing']['quality'],'unsynchronized')

    def test_unknown_sensor_does_not_poison_node_sequence(self):
        c,m=setup_manager()
        self.assertFalse(m.accept(replace(sample(),sensor_id='bad'),'wire'))
        self.assertTrue(m.accept(sample(),'wire'))
