"""Experimental Classic-CAN fragmentation codec, NOT an MCP2515 driver.

One sender owns each CAN ID. Byte 0 transfer id, 1 index, 2 count, 3..7 data.
Envelope = uint16 BE length + JSON bytes (no newline) + uint32 BE CRC32.
No padding; fragments are 8 bytes except the final fragment. See PROTOCOL.md.
"""
import struct
import zlib
from ..protocol import MAX_FRAME, ProtocolError


def fragment(payload, transfer_id):
    payload = payload.rstrip(b'\r\n')
    if not 1 <= len(payload) <= MAX_FRAME or type(transfer_id) is not int or not 0 <= transfer_id <= 255:
        raise ProtocolError('CAN payload/id out of bounds')
    envelope = struct.pack('>H', len(payload)) + payload + struct.pack('>I', zlib.crc32(payload))
    count = (len(envelope)+4)//5
    return [bytes((transfer_id, i, count))+envelope[i*5:(i+1)*5] for i in range(count)]


class Reassembler:
    def __init__(self, timeout_s=0.5, max_inflight=16):
        self.timeout_s, self.max_inflight = timeout_s, max_inflight
        self.pending = {}
        self.expired = 0

    def expire(self, now):
        old = [k for k, v in self.pending.items() if now-v['start'] >= self.timeout_s]
        for k in old:
            del self.pending[k]
        self.expired += len(old)
        return len(old)

    def feed(self, can_id, data, now):
        self.expire(now)
        if type(can_id) is not int or not 0 <= can_id <= 0x1FFFFFFF or not isinstance(data, bytes) or not 4 <= len(data) <= 8:
            raise ProtocolError('invalid CAN frame')
        tid, index, count = data[:3]
        if not 2 <= count <= (MAX_FRAME+10)//5 or index >= count or index < count-1 and len(data) != 8:
            raise ProtocolError('invalid CAN fragment header')
        key = (can_id, tid)
        if index == 0:
            if key in self.pending:
                del self.pending[key]
                raise ProtocolError('duplicate CAN start')
            if len(self.pending) >= self.max_inflight:
                raise ProtocolError('CAN reassembly capacity reached')
            self.pending[key] = {'start':now, 'next':0, 'count':count, 'data':bytearray()}
        item = self.pending.get(key)
        if item is None:
            raise ProtocolError('CAN fragment without start')
        if index != item['next'] or count != item['count']:
            del self.pending[key]
            raise ProtocolError('CAN duplicate/order/count mismatch')
        item['data'].extend(data[3:])
        item['next'] += 1
        if index != count-1:
            return None
        del self.pending[key]
        blob = bytes(item['data'])
        length = int.from_bytes(blob[:2], 'big')
        if not 1 <= length <= MAX_FRAME or len(blob) != length+6:
            raise ProtocolError('CAN envelope length mismatch')
        payload = blob[2:-4]
        if zlib.crc32(payload) != int.from_bytes(blob[-4:], 'big'):
            raise ProtocolError('CAN envelope CRC mismatch')
        return payload
