"""Seeded simulation; explicit step(now) permits fast tests with no sleeping."""
import math
import random
import threading
from ..protocol import Message, encode
from .sensors import GENERATORS
from .patient import SCENARIOS, patient_state, pressure_proxy, cpr_proxy, ecg_trace


class Simulator:
    def __init__(self, service, specs, enabled=None, seed=7, scenario='normal'):
        self.service, self.specs = service, {s.sensor_id:s for s in specs}
        self.enabled = set(self.specs if enabled is None else enabled)
        unknown = self.enabled - GENERATORS.keys()
        if unknown:
            raise ValueError('no simulator for: '+','.join(sorted(unknown)))
        self.randoms = {sid:random.Random(str(seed)+':'+sid) for sid in self.specs}

        if scenario not in SCENARIOS:
            raise ValueError('unknown simulation scenario')
        self.scenario = scenario
        self.start = service.manager.clock()
        self.scenario_start = self.start
        self.paused = False
        self.overrides = {}
        self.airway_override = None
        self.compressions_on = False
        self.ventilation_on = False
        # Engineering DEMO controls only, not patient safety or clinical limits.
        self.manual_limits = {
            'pressure': (-600, 900, 1, 'ADC counts'),
            'head_imu': (-90, 90, 1, 'rotation °'),
            'chest_imu': (-90, 90, 1, 'rotation °'),
            'cpr': (0, 40, 1, 'N (synthetic)'),
            'temperature': (30, 40, 0.1, '°C (synthetic)'),
            'spo2': (0, 100, 1, '% (synthetic)'),
        }
        self.sessions, self.seq, self.boot_count = {}, {}, {}
        self.delayed = []
        self.lock = threading.Lock()
        self.last_tick = None

    def control_state(self):
        with self.lock:
            return {'enabled':sorted(self.enabled), 'available':sorted(self.specs),
                    'paused':self.paused, 'scenario':self.scenario,
                    'scenarios': [{'id':sid,'label':label,'description':desc}
                                  for sid,(label,desc) in SCENARIOS.items()],
                    'airway_override':self.airway_override,
                    'compressions_on':self.compressions_on,
                    'ventilation_on':self.ventilation_on,
                    'scenario_elapsed_s':max(0, self.service.manager.clock()-self.scenario_start),
                    'overrides':dict(self.overrides),
                    'limits':{sid:{'min':lo,'max':hi,'step':step,'label':label}
                              for sid,(lo,hi,step,label) in self.manual_limits.items()
                              if sid in self.specs}}

    def set_enabled(self, sid, enabled):
        if sid not in self.specs or sid not in GENERATORS:
            raise ValueError('unknown simulator sensor')
        with self.lock:
            if enabled:
                self.enabled.add(sid)
                self.randoms[sid]
            else:
                self.enabled.discard(sid)
                self.delayed = [(due, msg) for due, msg in self.delayed if msg.sensor_id != sid]

    def set_paused(self, paused):
        if type(paused) is not bool:
            raise ValueError('paused must be boolean')
        with self.lock:
            self.paused = paused
            if paused:
                self.delayed.clear()

    def set_scenario(self, scenario):
        if scenario not in SCENARIOS:
            raise ValueError('unknown simulation scenario')
        with self.lock:
            self.scenario = scenario
            self.scenario_start = self.service.manager.clock()
            self.airway_override = None
            self.compressions_on = False
            self.ventilation_on = False
            for sid in ('pressure', 'spo2', 'cpr'):
                self.overrides.pop(sid, None)
            # In-flight delayed samples from an old scenario are not meaningful.
            self.delayed.clear()

    def set_airway_obstruction(self, percent):
        if percent is not None and (type(percent) not in (int, float) or
                                    not math.isfinite(percent) or not 0 <= percent <= 100):
            raise ValueError('airway obstruction must be 0..100 or null')
        with self.lock:
            self.airway_override = float(percent) if percent is not None else None

    def set_intervention(self, kind, enabled):
        if kind not in ('compressions', 'ventilation') or type(enabled) is not bool:
            raise ValueError('invalid simulated intervention')
        with self.lock:
            if kind == 'compressions':
                self.compressions_on = enabled
            else:
                self.ventilation_on = enabled

    def patient_snapshot(self):
        with self.lock:
            now = self.service.manager.clock()
            elapsed = max(0, now-self.scenario_start)
            state = patient_state(self.scenario,elapsed,self.airway_override,
                                  self.compressions_on,self.ventilation_on)
            state['ecg_preview'] = ecg_trace(max(0,now-self.start), state)
            return state

    def set_override(self, sid, value):
        if sid not in self.specs or sid not in self.manual_limits:
            raise ValueError('manual override unavailable for sensor')
        if value is not None:
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError('override must be finite numeric or null')
            low, high, _, _ = self.manual_limits[sid]
            if not low <= value <= high:
                raise ValueError('override outside demonstration range')
        with self.lock:
            if value is None:
                self.overrides.pop(sid, None)
            else:
                self.overrides[sid] = float(value)

    def restart(self, node):
        with self.lock:
            self.sessions.pop(node, None)

    def _send(self, m):
        # Exercise the same serialization, decoder and manager as physical JSONL.
        self.service.receive_line(encode(m), 'sim:'+m.node_id)

    def _next(self, node):
        seq = self.seq[node]
        self.seq[node] = (seq+1) & 0xFFFFFFFF
        return seq

    def step(self, now=None):
        with self.lock:
            now = self.service.manager.clock() if now is None else now
            elapsed = max(0, now-self.start)
            scenario_elapsed = max(0, now-self.scenario_start)
            ticks = int(elapsed*1000) & 0xFFFFFFFF
            if ticks == self.last_tick:
                return
            self.last_tick = ticks
            # Pause means no synthetic measurements, allowing real stale/timeout
            # behavior to be exercised by the existing integration manager.
            if self.paused:
                return
            patient = patient_state(self.scenario,scenario_elapsed,self.airway_override,
                                    self.compressions_on,self.ventilation_on)
            # In the demo, stale first and then fully disconnected; automatic recovery.
            disconnected = 4 <= scenario_elapsed < 11 and self.scenario == 'demo'
            for sid in sorted(self.enabled):
                if sid == 'spo2' and disconnected:
                    continue
                spec = self.specs[sid]
                node = spec.node_id
                if node not in self.sessions:
                    count = self.boot_count.get(node, 0)+1
                    self.boot_count[node] = count
                    self.sessions[node] = 'sim-'+node+'-'+str(count)
                    self.seq[node] = 0
                    self._send(Message(1,'hello',node,self.sessions[node],self._next(node),ticks,
                                       meta={'simulated':True}))
                    # All mock nodes are generated from THIS host clock, so this
                    # mapping is known exactly; do not copy it to independent MCUs.
                    self.service.manager.install_time_mapping(node,self.sessions[node],self.start,0,86400)
                value, meta = GENERATORS[sid](elapsed, self.randoms[sid])
                if sid == 'pressure':
                    value = pressure_proxy(elapsed, patient, self.randoms[sid])
                    meta = {'model':'fictional airway-pressure ADC excursion',
                            'scenario':self.scenario,'airflow_proxy_percent':patient['airflow_proxy_percent']}
                elif sid == 'cpr':
                    value = cpr_proxy(elapsed, patient)
                    meta = {'model':'fictional compression-force excursion', 'compressions_on':self.compressions_on}
                elif sid == 'spo2':
                    value = patient['spo2_target_percent'] + self.randoms[sid].uniform(-0.15,0.15)
                    value = max(0,min(100,round(value,2)))
                    meta = {'model':'operator-authored synthetic saturation curve','scenario':self.scenario}
                if sid in self.overrides:
                    fixed = self.overrides[sid]
                    if sid in ('head_imu', 'chest_imu'):
                        a = math.radians(fixed)/2
                        value = [math.cos(a), 0, math.sin(a), 0]
                        meta = {'frame_id':'sim_world', 'mounting_calibrated':True,
                                'manual_override_deg':fixed, 'model':'synthetic rotation'}
                    else:
                        value = fixed
                        meta = {'manual_override':True, 'model':'operator-defined test fixture'}
                invalid = self.scenario == 'demo' and sid == 'pressure' and 6 <= scenario_elapsed < 8
                m = Message(1,'measurement',node,self.sessions[node],self._next(node),ticks,
                    sensor_id=sid, measurement=spec.measurement, value=None if invalid else value,
                    unit=spec.unit, status='invalid' if invalid else 'ok', valid=not invalid,
                    calibration='simulated', error='SIMULATED_ADC_FAULT' if invalid else None, meta=meta)
                if self.scenario == 'demo' and sid == 'head_imu' and 3 <= scenario_elapsed < 4:
                    self.delayed.append((now+1.5,m))
                else:
                    self._send(m)
            due = [m for due,m in self.delayed if due <= now]
            self.delayed = [(due,m) for due,m in self.delayed if due > now]
            for m in due:
                self._send(m)

    def run(self, stop, period_s=0.1):
        while not stop.is_set():
            self.step()
            stop.wait(period_s)
