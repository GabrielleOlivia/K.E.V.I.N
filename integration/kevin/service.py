"""Application ingress: parsing, audit logging and the manager meet here."""
import sys
from .protocol import decode, ProtocolError, MAX_FRAME


class IntegrationService:
    def __init__(self, manager, eventlog=None):
        self.manager, self.log = manager, eventlog
        self.log_fault_reported = False

    def record(self, kind, **fields):
        if self.log and not self.log.write(kind, **fields) and not self.log_fault_reported:
            self.log_fault_reported = True
            self.manager.diagnostic('logging_failed', self.log.error)
            print('LOGGING FAILED: '+str(self.log.error), file=sys.stderr, flush=True)

    def receive(self, message, source):
        accepted = self.manager.accept(message, source)
        # Validate log representation separately: invalid JSON values must never
        # poison the audit logger or crash the acquisition worker.
        if accepted:
            self.record('message', source=source, received_host_s=self.manager.clock(),
                        accepted=True, message=message.to_dict() if hasattr(message, 'to_dict') else message)
        else:
            self.record('rejected', source=source, received_host_s=self.manager.clock(),
                        reason=self.manager.snapshot()['events'][-1]['detail'])
        return accepted

    def decode_line(self, line, source, adapter=None):
        self.record('wire', source=source, received_host_s=self.manager.clock(),
                    line=line[:MAX_FRAME].decode('ascii', errors='backslashreplace') if isinstance(line, bytes) else str(line)[:MAX_FRAME],
                    truncated=len(line)>MAX_FRAME+2)
        try:
            messages = adapter.feed(line) if adapter else [decode(line)]
            if adapter and adapter.diagnostic:
                self.manager.diagnostic('device_comment', adapter.diagnostic)
            return messages
        except ProtocolError as exc:
            self.manager.diagnostic('parse_error', str(exc))
            self.record('parse_error', source=source, error=str(exc))
            return []

    def receive_line(self, line, source, adapter=None):
        return [self.receive(m, source) for m in self.decode_line(line, source, adapter)]

    def snapshot(self):
        return self.manager.snapshot()
