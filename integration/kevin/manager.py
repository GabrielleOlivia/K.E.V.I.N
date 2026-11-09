"""Thread-safe integration boundary. No transport, sensor driver or UI imports."""
from collections import Counter, deque
from copy import deepcopy
from dataclasses import dataclass, field
import math
import threading
import time
from .protocol import Message, ProtocolError, validate, newer_u32
from .registry import SensorSpec
from .timebase import NodeClock, TimeMapping
from .processing import relative_orientation


@dataclass
class Node:
    boot: str
    source: str
    seq: int
    last_seen: float
    clock: NodeClock = field(default_factory=NodeClock)
    fault: str | None = None
    link_down: bool = False
    simulated: bool = False


class SensorManager:
    def __init__(self, specs, clock=time.monotonic, expected_sources=None):
        self.clock = clock
        self.specs = {s.sensor_id: s for s in specs}
        if not self.specs or len(self.specs) != len(specs):
            raise ValueError('registry must be nonempty and unique')
        self.expected_sources = dict(expected_sources or {})
        self.nodes = {}
        self.retired = {s.node_id: set() for s in specs}
        self.readings = {}
        self.sensor_faults = {}
        self._lock = threading.RLock()
        self.counters = Counter()
        self.events = deque(maxlen=100)
        self.revision = 0

    def _event(self, code, detail, now):
        self.events.append({'at_host_s': now, 'code': code, 'detail': detail[:240]})

    def diagnostic(self, code, detail):
        with self._lock:
            self.counters[code] += 1
            self._event(code, str(detail), self.clock())

    def transport_lost(self, source, reason):
        with self._lock:
            for n in self.nodes.values():
                if n.source == source:
                    n.link_down = True
            self.diagnostic('transport_lost', source + ': ' + str(reason))

    def install_time_mapping(self, node_id, boot_id, offset_s, uncertainty_s, lifetime_s=30):
        """Install an externally established mapping, scoped to the current boot.

        No network clock synchronization is claimed. Production mappings need a
        measured offset/uncertainty from a synchronizer or common acquisition clock.
        """
        vals = (offset_s, uncertainty_s, lifetime_s)
        if any(type(x) not in (int, float) or not math.isfinite(x) for x in vals) or uncertainty_s < 0 or lifetime_s <= 0:
            raise ValueError('invalid clock mapping')
        with self._lock:
            n = self.nodes[node_id]
            if n.boot != boot_id:
                raise ValueError('mapping boot mismatch')
            n.clock.mapping = TimeMapping(offset_s, uncertainty_s, self.clock()+lifetime_s)

    def accept(self, message, source):
        """Return acceptance without raising on bad input. Rejections never refresh age."""
        with self._lock:
            now = self.clock()
            try:
                m = validate(message.to_dict() if isinstance(message, Message) else message)
                self._accept(m, source, now)
            except (ProtocolError, ValueError, TypeError, OverflowError, RecursionError) as exc:
                self.counters['rejected'] += 1
                self._event('rejected', str(exc), now)
                return False
            self.counters['accepted'] += 1
            self.revision += 1
            return True

    def _accept(self, m, source, now):
        if m.node_id not in self.retired:
            raise ProtocolError('unknown node: ' + m.node_id)
        expected = self.expected_sources.get(m.node_id)
        if expected is not None and source != expected:
            raise ProtocolError('node arrived on unassigned transport')
        if not isinstance(source, str) or not source:
            raise ProtocolError('transport provenance missing')
        if m.sensor_id is not None:
            spec = self.specs.get(m.sensor_id)
            if spec is None or spec.node_id != m.node_id:
                raise ProtocolError('unknown sensor or wrong node')
            if m.type == 'measurement':
                spec.check(m)
        n = self.nodes.get(m.node_id)
        new_boot = n is None or m.boot_id != n.boot
        if new_boot:
            if m.type != 'hello':
                raise ProtocolError('new boot must begin with hello')
            if m.boot_id in self.retired[m.node_id]:
                raise ProtocolError('retired boot replay')
            if n and n.source != source:
                raise ProtocolError('transport binding changed')
            if len(self.retired[m.node_id]) >= 1024:
                raise ProtocolError('boot history limit; operator restart required')
            replacement = Node(m.boot_id, source, m.seq, now,
                               simulated=m.meta.get('simulated') is True)
            replacement.clock.observe(m.t_ms, now)
            if n:
                self.retired[m.node_id].add(n.boot)
                self.counters['restarts'] += 1
            self.nodes[m.node_id] = replacement
            for sensor, spec in self.specs.items():
                if spec.node_id == m.node_id:
                    self.readings.pop(sensor, None)
                    self.sensor_faults.pop(sensor, None)
            self._event('hello', m.node_id + ' boot=' + m.boot_id, now)
            if m.status != 'ok':
                replacement.fault = m.error or 'initialization invalid'
            return
        if source != n.source:
            raise ProtocolError('transport binding changed')
        if not newer_u32(m.seq, n.seq):
            raise ProtocolError('duplicate or out-of-order sequence')
        previous = self.readings.get(m.sensor_id)
        if m.type == 'measurement' and previous and m.t_ms == previous['raw_t_ms']:
            raise ProtocolError('repeated acquisition timestamp')
        # Observe on a copy: rejected time/value must not mutate the live clock.
        clock = deepcopy(n.clock)
        timing = clock.observe(m.t_ms, now)
        gap = ((m.seq-n.seq) & 0xFFFFFFFF)-1
        n.seq, n.last_seen, n.link_down, n.clock = m.seq, now, False, clock
        self.counters['sequence_gaps'] += gap
        if m.type == 'measurement':
            self.readings[m.sensor_id] = {
                'value': deepcopy(m.value), 'valid': m.valid, 'status': m.status,
                'calibration': m.calibration, 'error': m.error,
                'meta': deepcopy(m.meta), 'received_s': now, 'timing': timing,
                'seq': m.seq, 'boot_id': m.boot_id, 'raw_t_ms': m.t_ms,
            }
            if m.status == 'fault':
                self.sensor_faults[m.sensor_id] = m.error
            elif m.valid:
                self.sensor_faults.pop(m.sensor_id, None)
        elif m.type in ('fault', 'status'):
            if m.sensor_id:
                if m.status == 'ok':
                    self.sensor_faults.pop(m.sensor_id, None)
                else:
                    self.sensor_faults[m.sensor_id] = m.error
            elif m.status == 'ok':
                n.fault = None
            else:
                n.fault = m.error
        elif m.status != 'ok':
            n.fault = m.error

    def snapshot(self):
        with self._lock:
            now = self.clock()
            channels = {}
            for sid, spec in self.specs.items():
                n, r = self.nodes.get(spec.node_id), self.readings.get(sid)
                state, reason = 'missing', 'no hello received'
                age = None if r is None else max(0, now-r['received_s']) + r['timing']['excess_delay_s']
                calibration = 'unknown' if r is None else r['calibration']
                valid = False
                if n:
                    link_age = max(0, now-n.last_seen)
                    if n.link_down or link_age >= spec.disconnect_s:
                        state, reason = 'disconnected', 'transport lost or node timeout'
                    elif n.fault or self.sensor_faults.get(sid):
                        state, reason = 'faulty', n.fault or self.sensor_faults[sid]
                    elif r is None:
                        state, reason = 'initializing', 'waiting for measurement'
                    elif age >= spec.stale_s:
                        state, reason = 'stale', 'measurement age exceeds configured limit'
                    elif not r['valid'] or r['status'] != 'ok':
                        state, reason = 'invalid', r['error'] or 'source marked sample invalid'
                    elif spec.calibration_required and not (calibration == 'calibrated' or calibration == 'baseline' and spec.baseline_allowed or calibration == 'simulated' and n.simulated):
                        state, reason = 'invalid', 'calibration unavailable'
                    else:
                        state, reason, valid = 'active', None, True
                timing = deepcopy(r['timing']) if r else None
                if timing and timing.get('mapping_expires_at') is not None and now > timing['mapping_expires_at']:
                    timing.update(mapped_host_s=None, uncertainty_s=None, quality='mapping_expired')
                channels[sid] = {
                    'node_id': spec.node_id, 'measurement': spec.measurement, 'unit': spec.unit,
                    'state': state, 'valid': valid, 'reason': reason,
                    'value': deepcopy(r['value']) if valid else None,
                    'last_received_value': deepcopy(r['value']) if r else None,
                    'age_s': age, 'received_host_s': r['received_s'] if r else None,
                    'timing': timing,
                    'seq': r['seq'] if r else None, 'boot_id': n.boot if n else None,
                    'calibration': calibration, 'meta': deepcopy(r['meta']) if r else {},
                    'source': n.source if n else None, 'simulated': n.simulated if n else False,
                }
            return {'schema_version': 1, 'revision': self.revision, 'host_monotonic_s': now,
                    'purpose': 'educational manikin integration; no clinical interpretation',
                    'channels': channels, 'derived': {'relative_rotation_deg': relative_orientation(channels)},
                    'diagnostics': dict(self.counters), 'events': deepcopy(list(self.events))}
