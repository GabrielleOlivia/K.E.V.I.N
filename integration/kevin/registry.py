"""Configuration-owned sensor contracts. Add sensors here, not in the manager."""
from dataclasses import dataclass, asdict
import json
import math
from pathlib import Path
from .protocol import ID, ProtocolError


@dataclass(frozen=True)
class SensorSpec:
    sensor_id: str
    node_id: str
    measurement: str
    unit: str
    shape: str = 'scalar'
    stale_s: float = 2.0
    disconnect_s: float = 6.0
    minimum: float | None = None
    maximum: float | None = None
    calibration_required: bool = True
    baseline_allowed: bool = False

    def __post_init__(self):
        for value in (self.sensor_id, self.node_id, self.measurement):
            if not isinstance(value, str) or not ID.fullmatch(value):
                raise ValueError('invalid registry identifier')
        if self.shape not in ('scalar', 'quaternion') or not isinstance(self.unit, str) or not self.unit:
            raise ValueError('invalid shape/unit')
        if not (0 < self.stale_s < self.disconnect_s < 86400):
            raise ValueError('require 0 < stale_s < disconnect_s < 86400')
        if type(self.calibration_required) is not bool or type(self.baseline_allowed) is not bool:
            raise ValueError('calibration_required must be boolean')
        for bound in (self.minimum, self.maximum):
            if bound is not None and (type(bound) not in (int, float) or not math.isfinite(bound)):
                raise ValueError('invalid bounds')
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError('inverted bounds')

    def check(self, m):
        if (m.node_id, m.measurement, m.unit) != (self.node_id, self.measurement, self.unit):
            raise ProtocolError('sensor node/type/unit does not match registry')
        if not m.valid:
            return
        if self.shape == 'scalar':
            if type(m.value) not in (float, int):
                raise ProtocolError('expected scalar')
            if self.minimum is not None and m.value < self.minimum or self.maximum is not None and m.value > self.maximum:
                raise ProtocolError('value outside configured engineering bounds')
        else:
            if not isinstance(m.value, list) or len(m.value) != 4:
                raise ProtocolError('expected quaternion [w,x,y,z]')
            norm = math.sqrt(sum(v*v for v in m.value))
            if not 0.98 <= norm <= 1.02:
                raise ProtocolError('quaternion norm outside 0.98..1.02')


def load_registry(path=None):
    path = Path(path) if path else Path(__file__).with_name('default_sensors.json')
    items = json.loads(path.read_text(encoding='utf-8'))
    specs = [SensorSpec(**item) for item in items]
    if not specs or len({s.sensor_id for s in specs}) != len(specs):
        raise ValueError('empty registry or duplicate sensor_id')
    return specs
