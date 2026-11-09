"""Adapter for preserved pressure firmware. Never infer kPa, flow or volume."""
import csv
import uuid
from ..protocol import Message, ProtocolError, U32

COLUMNS = 't_ms,raw,baseline,delta,state,candidate_count,sample_ok,baseline_ok'
STATES = {'IDLE', 'POSITIVE_EVENT', 'NEGATIVE_EVENT', 'CAL_REQUIRED', 'CALIBRATING'}


class PressureCSV:
    def __init__(self, node_id='pressure_node', sensor_id='pressure', session_factory=None):
        self.node_id, self.sensor_id = node_id, sensor_id
        self.session_factory = session_factory or (lambda: uuid.uuid4().hex)
        self.boot, self.seq, self.last_t = None, 0, None
        self.pending_restart = False
        self.diagnostic = None

    def _message(self, kind, ticks, **kwargs):
        m = Message(1, kind, self.node_id, self.boot, self.seq, ticks, **kwargs)
        self.seq = (self.seq+1) & U32
        return m

    def feed(self, line):
        self.diagnostic = None
        try:
            if isinstance(line, bytes):
                line = line.decode('ascii')
            text = line.strip()
            if not text:
                return []
            if text.startswith('#'):
                self.diagnostic = text
                return []
            if text == COLUMNS:
                if self.boot is not None:
                    self.pending_restart = True
                return []
            row = next(csv.reader([text], strict=True))
            if len(row) != 8:
                raise ValueError('expected exactly eight CSV fields')
            ts, raw, base, delta, state, count, sample, baseline = row
            if sample not in ('0', '1') or baseline not in ('0', '1') or state not in STATES:
                raise ValueError('bad flags or state')
            ticks, count = int(ts), int(count)
            if not 0 <= ticks <= U32 or not 0 <= count <= U32:
                raise ValueError('timestamp/count outside uint32')
            sample_ok, baseline_ok = sample == '1', baseline == '1'
            raw = int(raw) if raw else None
            base = int(base) if base else None
            delta = int(delta) if delta else None
            if sample_ok != (raw is not None) or baseline_ok != (base is not None):
                raise ValueError('fields disagree with validity flags')
            if any(x is not None and not -32768 <= x <= 32767 for x in (raw, base)):
                raise ValueError('ADC field outside signed 16-bit range')
            if sample_ok and baseline_ok:
                if delta is None or delta != raw-base or state in ('CAL_REQUIRED', 'CALIBRATING'):
                    raise ValueError('delta/state inconsistent with baseline')
            elif delta is not None or state not in ('CAL_REQUIRED', 'CALIBRATING'):
                raise ValueError('invalid sample must not claim event/delta')
            messages = []
            # Ordered UART cannot reorder rows. Regression therefore creates a new
            # inferred adapter session except for a plausible millis() rollover.
            regression = self.last_t is not None and ticks < self.last_t
            rollover = regression and self.last_t > 0xF0000000 and ticks < 0x0FFFFFFF
            if self.boot is None or self.pending_restart or regression and not rollover:
                self.boot, self.seq, self.last_t = self.session_factory(), 0, None
                self.pending_restart = False
                messages.append(self._message('hello', ticks, meta={
                    'adapter':'legacy_pressure_csv', 'boot_identity':'inferred_session', 'simulated':False}))
            if ticks == self.last_t:
                raise ValueError('duplicate pressure timestamp')
            self.last_t = ticks
            valid = sample_ok and baseline_ok
            error = None if valid else 'ADC_READ_FAILED' if not sample_ok else 'BASELINE_UNAVAILABLE'
            cal = 'baseline' if baseline_ok else 'calibrating' if state == 'CALIBRATING' else 'uncalibrated'
            messages.append(self._message('measurement', ticks, sensor_id=self.sensor_id,
                measurement='pressure_delta', value=delta if valid else None, unit='adc_count',
                valid=valid, status='ok' if valid else 'invalid', calibration=cal, error=error,
                meta={'raw':raw, 'baseline':base, 'delta':delta, 'state':state,
                      'candidate_count':count, 'sample_ok':sample_ok, 'baseline_ok':baseline_ok,
                      'timestamp_semantics':'read_completion', 'pressure_calibrated':False}))
            return messages
        except (ValueError, TypeError, UnicodeError, csv.Error, StopIteration) as exc:
            raise ProtocolError('pressure CSV: ' + str(exc)) from exc
