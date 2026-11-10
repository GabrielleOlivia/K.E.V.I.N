"""Summarize a saved IMU probe log, without claiming physical validation."""
from __future__ import annotations
import re
from pathlib import Path
import argparse

LINE = re.compile(r"^# (?P<bus>A|B) BHI candidate (?P<address>0x[0-9A-Fa-f]{2}) (?P<status>.*)$")


def summarize(text: str) -> dict[str, str]:
    """Return most recent device observation per bus/address."""
    latest: dict[str, str] = {}
    for line in text.splitlines():
        match = LINE.fullmatch(line.strip())
        if match:
            key = f"{match['bus']}:{match['address'].lower()}"
            latest[key] = match['status']
    return latest


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('log_file', type=Path)
    args = p.parse_args()
    for device, status in sorted(summarize(args.log_file.read_text(encoding='utf-8', errors='replace')).items()):
        print(f"{device}: {status}")


if __name__ == '__main__':
    main()
