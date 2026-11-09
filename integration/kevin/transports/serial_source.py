"""USB/UART worker with finite reads, reconnect and deterministic shutdown."""
import threading
from .framing import LineFramer
from ..adapters.pressure_csv import PressureCSV


class SerialSource(threading.Thread):
    def __init__(self, service, port, source, mode='jsonl', baud=115200, stop=None,
                 serial_factory=None, reconnect_s=1.0, session_handshake=False):
        super().__init__(name='serial-'+source, daemon=True)
        self.service, self.port, self.source, self.mode = service, port, source, mode
        self.baud, self.stop = baud, stop or threading.Event()
        self.serial_factory, self.reconnect_s = serial_factory, reconnect_s
        self.session_handshake = session_handshake

    def run(self):
        factory = self.serial_factory
        if factory is None:
            from serial import Serial
            factory = Serial
        while not self.stop.is_set():
            try:
                with factory(self.port, baudrate=self.baud, timeout=0.1, write_timeout=0.5) as connection:
                    self.service.manager.diagnostic('transport_open', self.source+' '+self.port)
                    if self.session_handshake:
                        import uuid
                        # Only the supplied mock-node example understands this;
                        # never send it to the preserved pressure firmware.
                        connection.write(('SESSION '+uuid.uuid4().hex+'\n').encode('ascii'))
                    framer = LineFramer()
                    adapter = PressureCSV() if self.mode == 'pressure' else None
                    previous_overflows = 0
                    while not self.stop.is_set():
                        chunk = connection.read(256)
                        if not chunk:
                            continue
                        for line in framer.feed(chunk):
                            if self.session_handshake and line == b'# SESSION_REQUIRED':
                                import uuid
                                connection.write(('SESSION '+uuid.uuid4().hex+'\n').encode('ascii'))
                                continue
                            self.service.receive_line(line, self.source, adapter)
                        if framer.overflows != previous_overflows:
                            self.service.manager.diagnostic('framing_overflow', self.source)
                            previous_overflows = framer.overflows
            except (OSError, ValueError) as exc:
                self.service.manager.transport_lost(self.source, exc)
                self.service.record('transport_lost', source=self.source, error=str(exc))
                self.stop.wait(self.reconnect_s)
