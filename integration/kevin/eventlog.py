"""Thread-safe append-only JSONL logs with bounded rotation and visible failures."""
from datetime import datetime, timezone
from pathlib import Path
import json
import threading


class EventLog:
    def __init__(self, path, max_bytes=10_000_000, backups=3):
        if type(backups) is not int or backups < 1 or max_bytes < 128:
            raise ValueError('require backups >= 1 and max_bytes >= 128')
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_bytes, self.backups = max_bytes, backups
        self.lock = threading.Lock()
        self.file = self.path.open('a', encoding='utf-8')
        self.error = None

    def write(self, kind, **fields):
        record = {'logged_utc':datetime.now(timezone.utc).isoformat(), 'kind':kind, **fields}
        text = json.dumps(record, allow_nan=False, separators=(',', ':'))+'\n'
        with self.lock:
            try:
                if self.file.tell()+len(text.encode('utf-8')) > self.max_bytes:
                    self.file.close()
                    for i in range(self.backups, 0, -1):
                        src = self.path if i == 1 else Path(str(self.path)+'.'+str(i-1))
                        dest = Path(str(self.path)+'.'+str(i))
                        if src.exists():
                            src.replace(dest)
                    self.file = self.path.open('a', encoding='utf-8')
                self.file.write(text)
                self.file.flush()
                return True
            except (OSError, ValueError) as exc:
                self.error = str(exc)
                return False

    def close(self):
        with self.lock:
            self.file.close()
