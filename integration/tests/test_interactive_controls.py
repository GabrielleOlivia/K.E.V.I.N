"""End-to-end synthetic control tests; no hardware connections are created."""
import http.client
import json
import math
import threading
import unittest
from kevin.registry import load_registry
from kevin.manager import SensorManager
from kevin.service import IntegrationService
from kevin.simulation.engine import Simulator
from kevin.dashboard import create_server
from tests.support import Clock


class SyntheticControlTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.specs = load_registry()
        self.manager = SensorManager(self.specs, self.clock,
                expected_sources={s.node_id: 'sim:' + s.node_id for s in self.specs})
        self.service = IntegrationService(self.manager)
        self.sim = Simulator(self.service, self.specs)

    def test_manual_scalar_control_and_reset(self):
        self.sim.set_override('pressure', 250)
        self.clock.advance(0.2)
        self.sim.step()
        r = self.manager.snapshot()['channels']['pressure']
        self.assertEqual(r['value'], 250)
        self.assertTrue(r['simulated'])
        self.assertTrue(r['meta']['manual_override'])
        self.sim.set_override('pressure', None)
        self.assertNotIn('pressure', self.sim.control_state()['overrides'])
        self.clock.advance(0.2)
        self.sim.step()
        self.assertNotIn('manual_override', self.manager.snapshot()['channels']['pressure']['meta'])

    def test_orientation_override_yields_normalized_quaternion(self):
        self.sim.set_override('head_imu', 60)
        self.sim.set_override('chest_imu', 10)
        self.clock.advance(0.2)
        self.sim.step()
        channels = self.manager.snapshot()['channels']
        for sid in ('head_imu', 'chest_imu'):
            q = channels[sid]['value']
            self.assertAlmostEqual(math.sqrt(sum(v*v for v in q)), 1, places=6)
        self.assertAlmostEqual(self.manager.snapshot()['derived']['relative_rotation_deg']['value'], 50, delta=0.001)

    def test_pause_and_resume_does_not_fabricate_data(self):
        self.clock.advance(0.2)
        self.sim.step()
        self.assertEqual(self.manager.snapshot()['channels']['pressure']['state'], 'active')
        self.sim.set_paused(True)
        self.clock.advance(6)
        self.sim.step()
        self.assertEqual(self.manager.snapshot()['channels']['pressure']['state'], 'disconnected')
        self.sim.set_paused(False)
        self.clock.advance(0.2)
        self.sim.step()
        self.assertEqual(self.manager.snapshot()['channels']['pressure']['state'], 'active')

    def test_invalid_operator_values_rejected_without_mutation(self):
        for bad in (True, float('nan'), float('inf'), 500000, -2000, '3', []):
            with self.assertRaises(ValueError):
                self.sim.set_override('pressure', bad)
        self.assertEqual(self.sim.control_state()['overrides'], {})
        with self.assertRaises(ValueError):
            self.sim.set_paused('true')
        with self.assertRaises(ValueError):
            self.sim.set_scenario('clinical')
        self.assertEqual(self.sim.control_state()['scenario'], 'normal')

    def test_scenario_restart(self):
        self.clock.advance(20)
        self.sim.set_scenario('demo')
        self.assertLess(self.sim.control_state()['scenario_elapsed_s'], 0.01)
        self.clock.advance(6.5)
        self.sim.step()
        self.assertEqual(self.manager.snapshot()['channels']['pressure']['state'], 'invalid')
        self.sim.set_scenario('normal')
        self.clock.advance(0.2)
        self.sim.step()
        self.assertEqual(self.manager.snapshot()['channels']['pressure']['state'], 'active')

    def test_http_control_validation_and_physical_ownership(self):
        server = create_server(self.service, self.sim, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            conn.request('GET','/api/state')
            response=conn.getresponse();state=json.loads(response.read())
            self.assertEqual(response.status,200)
            token=state['simulation_control']['token']
            def post(obj, auth=True):
                headers={'Content-Type':'application/json'}
                if auth: headers['X-KEVIN-Token']=token
                conn.request('POST','/api/simulation',body=json.dumps(obj),headers=headers)
                r=conn.getresponse();data=json.loads(r.read());return r.status,data
            self.assertEqual(post({'action':'pause','paused':True})[0],200)
            self.assertTrue(self.sim.control_state()['paused'])
            self.assertEqual(post({'action':'scenario','scenario':'demo'})[0],200)
            self.assertEqual(post({'action':'override','sensor_id':'pressure','value':300})[0],200)
            self.assertEqual(post({'action':'override','sensor_id':'pressure','value':None})[0],200)
            self.assertEqual(post({'action':'override','sensor_id':'pressure','value':100000})[0],400)
            self.assertEqual(post({'action':'pause','paused':'true'})[0],400)
            self.assertEqual(post({'action':'pause','paused':False},False)[0],403)
            self.assertEqual(post({'action':'override','sensor_id':'unknown','value':25})[0],400)
            self.assertEqual(post({'sensor_id':'pressure','enabled':False})[0],200)
            conn.close()
        finally:
            server.shutdown();server.server_close();thread.join(timeout=3)


if __name__ == '__main__':
    unittest.main()
