"""Incremental bounded line framing. Timeout/partial reads never become frames."""
from ..protocol import MAX_FRAME


class LineFramer:
    def __init__(self, limit=MAX_FRAME):
        self.limit, self.buffer, self.discarding = limit, bytearray(), False
        self.overflows = 0

    def feed(self, chunk):
        frames = []
        for b in chunk:
            if b == 10:
                if not self.discarding:
                    frames.append(bytes(self.buffer).rstrip(b'\r'))
                self.buffer.clear()
                self.discarding = False
            elif not self.discarding:
                self.buffer.append(b)
                if len(self.buffer) > self.limit:
                    self.buffer.clear()
                    self.discarding = True
                    self.overflows += 1
        return frames
