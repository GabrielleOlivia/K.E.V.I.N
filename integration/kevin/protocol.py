"""Strict bounded JSON Lines protocol; the transport owns framing and provenance."""
import json
import math
import re
from dataclasses import dataclass, field, asdict

MAX_FRAME = 1024
U32 = 0xFFFFFFFF
ID = re.compile(r'^[A-Za-z0-9_.:-]{1,64}$')
TYPES = {'hello', 'measurement', 'heartbeat', 'status', 'fault'}
CALIBRATIONS = {'unknown', 'uncalibrated', 'calibrating', 'baseline', 'calibrated', 'not_required', 'simulated'}


class ProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class Message:
    v: int
    type: str
    node_id: str
    boot_id: str
    seq: int
    t_ms: int
    clock: str = 'uptime_ms'
    sensor_id: str | None = None
    measurement: str | None = None
    value: float | int | list | None = None
    unit: str | None = None
    status: str = 'ok'
    valid: bool = False
    calibration: str = 'unknown'
    error: str | None = None
    meta: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


def _pairs(items):
    result = {}
    for k, v in items:
        if k in result:
            raise ProtocolError('duplicate JSON key: ' + k)
        result[k] = v
    return result


def _finite_tree(value, depth=0):
    if depth > 5:
        raise ProtocolError('metadata nesting exceeds 5')
    if isinstance(value, float) and not math.isfinite(value):
        raise ProtocolError('nonfinite number')
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise ProtocolError('keys must be strings')
            _finite_tree(v, depth+1)
    elif isinstance(value, list):
        for v in value:
            _finite_tree(v, depth+1)
    elif value is not None and type(value) not in (str, int, float, bool):
        raise ProtocolError('unsupported JSON value')


def validate(data):
    if not isinstance(data, dict):
        raise ProtocolError('message must be an object')
    required = {'v', 'type', 'node_id', 'boot_id', 'seq', 't_ms', 'clock'}
    if not required <= data.keys() or data.keys() - Message.__dataclass_fields__.keys():
        raise ProtocolError('missing envelope field or unknown field')
    _finite_tree(data)
    if type(data['v']) is not int or data['v'] != 1:
        raise ProtocolError('unsupported protocol version')
    for k in ('node_id', 'boot_id'):
        if not isinstance(data[k], str) or not ID.fullmatch(data[k]):
            raise ProtocolError('invalid ' + k)
    for k in ('seq', 't_ms'):
        if type(data[k]) is not int or not 0 <= data[k] <= U32:
            raise ProtocolError(k + ' must be uint32')
    if not isinstance(data['type'], str) or data['type'] not in TYPES:
        raise ProtocolError('unknown message type')
    if data['clock'] != 'uptime_ms':
        raise ProtocolError('wire clock must be uptime_ms; mappings are host-owned')
    m = Message(**data)
    if type(m.valid) is not bool or m.status not in ('ok', 'invalid', 'fault'):
        raise ProtocolError('invalid status/valid')
    if not isinstance(m.calibration, str) or m.calibration not in CALIBRATIONS:
        raise ProtocolError('invalid calibration')
    if not isinstance(m.meta, dict):
        raise ProtocolError('meta must be object')
    if m.error is not None and (not isinstance(m.error, str) or not 1 <= len(m.error) <= 160):
        raise ProtocolError('invalid error')
    if m.sensor_id is not None and (not isinstance(m.sensor_id, str) or not ID.fullmatch(m.sensor_id)):
        raise ProtocolError('invalid sensor_id')
    if m.status != 'ok' and not m.error:
        raise ProtocolError('invalid/fault status requires error')
    if m.valid and (m.status != 'ok' or m.type != 'measurement'):
        raise ProtocolError('only an ok measurement can be valid')
    if m.type == 'measurement':
        if m.sensor_id is None or not isinstance(m.measurement, str) or not ID.fullmatch(m.measurement):
            raise ProtocolError('measurement needs sensor_id and measurement type')
        if not isinstance(m.unit, str) or not 1 <= len(m.unit) <= 24:
            raise ProtocolError('measurement needs unit')
        if m.valid:
            vals = m.value if isinstance(m.value, list) else [m.value]
            if not 1 <= len(vals) <= 4 or any(type(v) not in (float, int) or abs(v) > 1e100 or not math.isfinite(v) for v in vals):
                raise ProtocolError('valid measurement needs finite numeric value(s)')
        elif m.value is not None:
            raise ProtocolError('invalid measurement must use null value')
    elif m.value is not None or m.measurement is not None or m.unit is not None:
        raise ProtocolError('control messages must not carry measurement fields')
    if m.type in ('hello', 'heartbeat') and m.sensor_id is not None:
        raise ProtocolError('hello/heartbeat are node-wide')
    if m.type == 'fault' and m.status != 'fault':
        raise ProtocolError('fault message must have fault status')
    try:
        size = len(json.dumps(data, allow_nan=False, separators=(',', ':')).encode('utf-8'))
    except (ValueError, TypeError, OverflowError) as exc:
        raise ProtocolError(str(exc)) from exc
    if size > MAX_FRAME:
        raise ProtocolError('frame too large')
    return m


def decode(line):
    try:
        raw = line.encode('utf-8') if isinstance(line, str) else line
        if not isinstance(raw, bytes) or len(raw.rstrip(b'\r\n')) > MAX_FRAME:
            raise ProtocolError('frame type/length invalid')
        data = json.loads(raw, object_pairs_hook=_pairs,
                          parse_constant=lambda x: (_ for _ in ()).throw(ProtocolError('nonfinite ' + x)))
        return validate(data)
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError) as exc:
        raise ProtocolError(str(exc)) from exc


def encode(message):
    m = validate(message.to_dict() if isinstance(message, Message) else message)
    payload = (json.dumps(m.to_dict(), allow_nan=False, separators=(',', ':')) + '\n').encode('utf-8')
    if len(payload)-1 > MAX_FRAME:
        raise ProtocolError('encoded frame too large')
    return payload


def newer_u32(current, previous):
    return 0 < ((current - previous) & U32) < 0x80000000
