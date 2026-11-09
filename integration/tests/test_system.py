import concurrent.futures
from dataclasses import replace
import json, math, shutil, subprocess, sys, tempfile, threading, unittest
from pathlib import Path
import urllib.request, urllib.error
from kevin.dashboard import create_server
from kevin.eventlog import EventLog
from kevin.service import IntegrationService
from kevin.simulation.engine import Simulator
from kevin.protocol import decode
from tests.support import *
ROOT=Path(__file__).resolve().parents[1]

class SimulationTests(unittest.TestCase):
    def make(self,scenario='normal'):
        c=Clock();specs=load_registry();m=SensorManager(specs,c)
        return c,m,Simulator(IntegrationService(m),specs,scenario=scenario)
    def test_six_sensors_end_to_end_and_geometry(self):
        c,m,s=self.make();c.advance(.2);s.step();state=m.snapshot()
        self.assertEqual(len(state['channels']),6)
        self.assertTrue(all(ch['valid'] and ch['simulated'] for ch in state['channels'].values()))
        self.assertTrue(state['derived']['relative_rotation_deg']['valid'])
        self.assertAlmostEqual(state['derived']['relative_rotation_deg']['value'],15*math.sin(.2),places=6)
    def test_individual_disable_recovery(self):
        c,m,s=self.make();s.step();s.set_enabled('pressure',False);c.advance(1.1);s.step()
        self.assertEqual(m.snapshot()['channels']['pressure']['state'],'stale')
        s.set_enabled('pressure',True);c.advance(.1);s.step()
        self.assertEqual(m.snapshot()['channels']['pressure']['state'],'active')
    def test_demo_fault_delay_disconnect_reconnection(self):
        c,m,s=self.make('demo');observed=set()
        for i in range(125):
            c.t=100+i/10;s.step();state=m.snapshot();observed.add(state['channels']['spo2']['state'])
            if i==70:self.assertEqual(state['channels']['pressure']['state'],'invalid')
        self.assertTrue({'active','stale','disconnected'}<=observed)
        self.assertEqual(state['channels']['spo2']['state'],'active');self.assertGreater(state['diagnostics']['rejected'],0)
    def test_seed_reproducibility(self):
        c,m,s=self.make();d,n,t=self.make()
        for _ in range(10):
            c.advance(.1);d.advance(.1);s.step();t.step()
            self.assertEqual(m.snapshot()['channels']['pressure']['value'],n.snapshot()['channels']['pressure']['value'])
    def test_restart(self):
        c,m,s=self.make();s.step();old=m.snapshot()['channels']['head_imu']['boot_id']
        s.restart('head_node');c.advance(.1);s.step()
        self.assertNotEqual(old,m.snapshot()['channels']['head_imu']['boot_id'])
    def test_no_geometry_without_time_mapping(self):
        c=Clock();m=SensorManager(load_registry(),c)
        for sid,node in (('head_imu','head_node'),('chest_imu','chest_node')):
            m.accept(hello(node=node),'wire'+sid)
            m.accept(sample(sensor=sid,node=node,value=[1,0,0,0],meta={'frame_id':'x','mounting_calibrated':True}),'wire'+sid)
        self.assertFalse(m.snapshot()['derived']['relative_rotation_deg']['valid'])
    def test_no_geometry_with_skew_or_frame_mismatch(self):
        c,m,s=self.make();s.step();c.advance(.2)
        m.accept(sample(seq=2,t=200,sensor='head_imu',node='head_node',boot=s.sessions['head_node'],value=[1,0,0,0],meta={'frame_id':'other','mounting_calibrated':True}),'sim:head_node')
        self.assertFalse(m.snapshot()['derived']['relative_rotation_deg']['valid'])

class LoggingTests(unittest.TestCase):
    def test_concurrent_log_and_rejections(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'events.jsonl';log=EventLog(path)
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as p:list(p.map(lambda i:log.write('test',i=i),range(100)))
            c,m=setup_manager();service=IntegrationService(m,log)
            service.receive(sample(),'wire');service.receive(replace(sample(),value=float('nan')),'wire');log.close()
            rows=[json.loads(l) for l in path.read_text().splitlines()]
            self.assertEqual(len(rows),102);self.assertEqual(rows[-1]['kind'],'rejected')
            self.assertEqual(len({r['i'] for r in rows[:100]}),100)
    def test_rotation_and_visible_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'events.jsonl';log=EventLog(path,max_bytes=250,backups=2)
            for i in range(10):self.assertTrue(log.write('test',i=i,text='x'*50))
            log.close();self.assertTrue(Path(str(path)+'.1').exists());self.assertFalse(Path(str(path)+'.3').exists())
            c,m=setup_manager();service=IntegrationService(m,log);service.record('test')
            self.assertEqual(m.snapshot()['diagnostics']['logging_failed'],1)

class DashboardTests(unittest.TestCase):
    def test_api_assets_and_controls(self):
        c=Clock();m=SensorManager(load_registry(),c);service=IntegrationService(m)
        sim=Simulator(service,[s for s in load_registry() if s.sensor_id!='pressure']);sim.step()
        server=create_server(service,sim,port=0);thread=threading.Thread(target=server.serve_forever);thread.start()
        url='http://127.0.0.1:'+str(server.server_port)
        try:
            for route in ('/','/app.js','/style.css'):self.assertEqual(urllib.request.urlopen(url+route,timeout=2).status,200)
            state=json.load(urllib.request.urlopen(url+'/api/state',timeout=2));token=state['simulation_control']['token']
            def post(sid,key):
                req=urllib.request.Request(url+'/api/simulation',data=json.dumps({'sensor_id':sid,'enabled':False}).encode(),headers={'Content-Type':'application/json','X-KEVIN-Token':key})
                return urllib.request.urlopen(req,timeout=2)
            self.assertEqual(post('head_imu',token).status,200)
            with self.assertRaises(urllib.error.HTTPError) as err:post('head_imu','bad')
            self.assertEqual(err.exception.code,403)
            with self.assertRaises(urllib.error.HTTPError):post('pressure',token)
            with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(url+'/../app.py',timeout=2)
        finally:server.shutdown();server.server_close();thread.join()

class ExecutableTests(unittest.TestCase):
    def test_simulation_cli_without_third_party(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'run.jsonl'
            r=subprocess.run([sys.executable,'-S','-m','kevin','--no-web','--duration','.6','--log',str(path)],cwd=ROOT,capture_output=True,text=True,timeout=8)
            self.assertEqual(r.returncode,0,r.stderr)
            rows=[json.loads(l) for l in path.read_text().splitlines()]
            self.assertTrue(all(s['valid'] for s in rows[-1]['state']['channels'].values()))
    @unittest.skipUnless(shutil.which('g++'),'g++ unavailable')
    def test_cpp_native_cross_language(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=str(Path(tmp)/'node')
            subprocess.run(['g++','-std=c++11','-Wall','-Wextra','-Werror','-I',str(ROOT/'firmware/node_example/include'),str(ROOT/'firmware/node_example/test_native/test_node.cpp'),'-o',out],check=True,capture_output=True,timeout=30)
            r=subprocess.run([out],check=True,capture_output=True,timeout=5)
            messages=[decode(line) for line in r.stdout.splitlines()];m=SensorManager(load_registry())
            self.assertTrue(all(m.accept(x,'cpp') for x in messages));self.assertEqual(m.snapshot()['channels']['head_imu']['state'],'invalid')
    @unittest.skipUnless(shutil.which('g++'),'g++ unavailable')
    def test_preserved_pressure_native_suite(self):
        root=ROOT/'firmware/pressure_legacy'
        with tempfile.TemporaryDirectory() as tmp:
            out=str(Path(tmp)/'pressure')
            subprocess.run(['g++','-std=c++11','-Wall','-Wextra','-Werror','-I',str(root/'tests/stubs'),str(root/'tests/pressure_logger_host_test.cpp'),'-o',out],check=True,capture_output=True,timeout=30)
            r=subprocess.run([out],check=True,capture_output=True,timeout=5);self.assertTrue(r.stdout)
