"""Patient-scenario tests verify software fixtures, not medical physiology."""
import http.client
import json
import threading
import unittest
from kevin.registry import load_registry
from kevin.manager import SensorManager
from kevin.service import IntegrationService
from kevin.simulation.engine import Simulator
from kevin.simulation.patient import SCENARIOS, patient_state, ecg_trace
from kevin.dashboard import create_server
from tests.support import Clock


class PatientScenarioTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.specs = load_registry()
        sources = {s.node_id: 'sim:'+s.node_id for s in self.specs}
        self.manager = SensorManager(self.specs,self.clock,expected_sources=sources)
        self.sim = Simulator(IntegrationService(self.manager),self.specs)

    def test_all_presets_are_available_and_bounded(self):
        self.assertGreaterEqual(len(SCENARIOS),8)
        for name in SCENARIOS:
            for seconds in (0,5,30,200):
                s=patient_state(name,seconds)
                self.assertEqual(s['scenario'],name)
                self.assertTrue(0 <= s['spo2_target_percent'] <= 100)
                self.assertTrue(0 <= s['airflow_proxy_percent'] <= 100)
                self.assertTrue(s['is_synthetic'])

    def test_asystole_is_not_silent_sensor_disconnection(self):
        self.sim.set_scenario('cardiac_arrest')
        self.clock.advance(0.2)
        self.sim.step()
        p=self.sim.patient_snapshot()
        self.assertEqual(p['heart_rate_bpm'],0)
        self.assertEqual(p['spontaneous_resp_rate_bpm'],0)
        self.assertFalse(p['pulse_present'])
        self.assertEqual(set(p['ecg_preview']),{0.0})
        self.assertEqual(self.manager.snapshot()['channels']['pressure']['state'],'active')
        self.assertTrue(self.manager.snapshot()['channels']['pressure']['simulated'])

    def test_vf_is_electrical_activity_without_pulse(self):
        self.sim.set_scenario('vf_arrest')
        p=self.sim.patient_snapshot()
        self.assertEqual(p['heart_rate_bpm'],0)
        self.assertEqual(p['rhythm'],'vf')
        self.assertFalse(p['pulse_present'])
        self.assertGreater(max(p['ecg_preview'])-min(p['ecg_preview']),0.2)

    def test_respiratory_arrest_and_ventilation(self):
        self.sim.set_scenario('respiratory_arrest')
        self.assertEqual(self.sim.patient_snapshot()['spontaneous_resp_rate_bpm'],0)
        self.assertEqual(self.sim.patient_snapshot()['airflow_proxy_percent'],0)
        self.assertGreater(self.sim.patient_snapshot()['heart_rate_bpm'],0)
        self.sim.set_intervention('ventilation',True)
        self.assertEqual(self.sim.patient_snapshot()['spontaneous_resp_rate_bpm'],0)
        self.assertEqual(self.sim.patient_snapshot()['airflow_proxy_percent'],100)
        self.clock.advance(0.7)
        self.sim.step()
        self.assertGreater(self.manager.snapshot()['channels']['pressure']['value'],0)

    def test_pinched_vs_complete_airway(self):
        self.sim.set_scenario('airway_partial')
        p=self.sim.patient_snapshot()
        self.assertEqual(p['airway_obstruction_percent'],65)
        self.assertEqual(p['airflow_proxy_percent'],35)
        self.sim.set_scenario('airway_complete')
        q=self.sim.patient_snapshot()
        self.assertEqual(q['airflow_proxy_percent'],0)
        self.assertTrue(q['spontaneous_resp_rate_bpm']>0)
        self.sim.set_airway_obstruction(30)
        self.assertEqual(self.sim.patient_snapshot()['airflow_proxy_percent'],70)
        self.sim.set_airway_obstruction(None)
        self.assertEqual(self.sim.patient_snapshot()['airway_obstruction_percent'],100)

    def test_cpr_does_not_restart_spontaneous_heart(self):
        self.sim.set_scenario('cardiac_arrest')
        self.sim.set_intervention('compressions',True)
        self.clock.advance(.21)
        self.sim.step()
        state=self.manager.snapshot()['channels']['cpr']
        self.assertTrue(state['valid'])
        self.assertGreater(state['value'],0)
        self.assertEqual(self.sim.patient_snapshot()['heart_rate_bpm'],0)

    def test_simulated_spo2_trends_and_sensor_feed(self):
        self.sim.set_scenario('respiratory_arrest')
        self.clock.advance(1)
        self.sim.step()
        early=self.manager.snapshot()['channels']['spo2']['value']
        self.clock.advance(30)
        self.sim.step()
        late=self.manager.snapshot()['channels']['spo2']['value']
        self.assertLess(late,early)
        self.assertTrue(self.manager.snapshot()['channels']['spo2']['simulated'])

    def test_scenario_switch_resets_interventions_and_related_manual_overrides(self):
        self.sim.set_override('spo2',85)
        self.sim.set_override('pressure',300)
        self.sim.set_override('head_imu',25)
        self.sim.set_airway_obstruction(95)
        self.sim.set_intervention('ventilation',True)
        self.sim.set_intervention('compressions',True)
        self.sim.set_scenario('normal')
        self.assertIsNone(self.sim.control_state()['airway_override'])
        self.assertFalse(self.sim.control_state()['compressions_on'])
        self.assertFalse(self.sim.control_state()['ventilation_on'])
        self.assertEqual(self.sim.control_state()['overrides'],{'head_imu':25.0})

    def test_input_validation(self):
        for bad in (True,'100',float('nan'),float('inf'),-1,101,[]):
            with self.assertRaises(ValueError):
                self.sim.set_airway_obstruction(bad)
        for kind,enabled in (('ventilation',1),('unknown',True),('compressions','true')):
            with self.assertRaises(ValueError):
                self.sim.set_intervention(kind,enabled)
        with self.assertRaises(ValueError):
            self.sim.set_scenario('fake-arrest')
        self.assertEqual(self.sim.control_state()['scenario'],'normal')

    def test_mixed_mode_does_not_write_to_unowned_pressure_node(self):
        remaining=[s for s in self.specs if s.sensor_id!='pressure']
        sources={s.node_id:'sim:'+s.node_id for s in remaining}
        sources['pressure_node']='serial:pressure'
        mgr=SensorManager(self.specs,self.clock,expected_sources=sources)
        sim=Simulator(IntegrationService(mgr),remaining)
        with self.assertRaises(ValueError):
            sim.set_override('pressure',500)
        sim.set_scenario('cardiac_arrest')
        self.clock.advance(0.3)
        sim.step()
        self.assertEqual(mgr.snapshot()['channels']['pressure']['state'],'missing')
        self.assertEqual(sim.patient_snapshot()['heart_rate_bpm'],0)

    def test_patient_control_api_authorization_and_validation(self):
        server=create_server(self.sim.service,self.sim,port=0)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            conn.request('GET','/api/state')
            response=conn.getresponse(); data=json.loads(response.read())
            self.assertEqual(response.status,200)
            self.assertTrue(data['simulated_patient']['is_synthetic'])
            token=data['simulation_control']['token']
            def post(obj,auth=True):
                conn.request('POST','/api/simulation',body=json.dumps(obj),headers={
                    'Content-Type':'application/json',
                    'X-KEVIN-Token':token if auth else 'wrong',
                })
                r=conn.getresponse(); return r.status,json.loads(r.read())
            self.assertEqual(post({'action':'scenario','scenario':'cardiac_arrest'})[0],200)
            self.assertEqual(post({'action':'airway','percent':80})[0],200)
            self.assertEqual(post({'action':'intervention','kind':'compressions','enabled':True})[0],200)
            self.assertEqual(post({'action':'intervention','kind':'ventilation','enabled':True})[0],200)
            self.assertEqual(post({'action':'airway','percent':101})[0],400)
            self.assertEqual(post({'action':'airway','percent':False})[0],400)
            self.assertEqual(post({'action':'intervention','kind':'ventilation','enabled':'yes'})[0],400)
            self.assertEqual(post({'action':'scenario','scenario':'cardiac_arrest'},False)[0],403)
            conn.request('GET','/api/state');r=conn.getresponse();s=json.loads(r.read())
            self.assertEqual(s['simulated_patient']['heart_rate_bpm'],0)
            self.assertEqual(s['simulated_patient']['airway_obstruction_percent'],80)
            conn.close()
        finally:
            server.shutdown();server.server_close();thread.join(timeout=3)


if __name__ == '__main__':
    unittest.main()
