"""Node uptime unwrapping and conservative receive-delay estimation."""
from dataclasses import dataclass
from .protocol import ProtocolError, U32


@dataclass
class TimeMapping:
    offset_s: float
    uncertainty_s: float
    expires_at: float


class NodeClock:
    def __init__(self):
        self.raw = None
        self.extended_ms = 0
        self.minimum_offset = None
        self.mapping = None

    def observe(self, ticks, received):
        if self.raw is None:
            extended = ticks
        else:
            advance = (ticks - self.raw) & U32
            if advance >= 0x80000000:
                raise ProtocolError('node timestamp regressed; new boot requires hello')
            extended = self.extended_ms + advance
        offset = received - extended / 1000
        minimum = offset if self.minimum_offset is None else min(offset, self.minimum_offset)
        mapped, uncertainty = None, None
        if self.mapping and received <= self.mapping.expires_at:
            mapped = extended / 1000 + self.mapping.offset_s
            uncertainty = self.mapping.uncertainty_s
            if mapped - uncertainty > received + 0.001:
                raise ProtocolError('mapped measurement is in the future')
            delay = max(0, received - mapped + uncertainty)
        else:
            delay = max(0, offset - minimum)
        self.raw, self.extended_ms, self.minimum_offset = ticks, extended, minimum
        return {'uptime_ms': extended, 'excess_delay_s': delay,
                'mapped_host_s': mapped, 'uncertainty_s': uncertainty,
                'mapping_expires_at': self.mapping.expires_at if mapped is not None else None,
                'quality': 'mapped' if mapped is not None else 'unsynchronized'}
