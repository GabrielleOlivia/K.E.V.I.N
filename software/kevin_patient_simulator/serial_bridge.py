"""Nonblocking bridge for K.E.V.I.N. v0.3 four-sensor serial diagnostics.

Supports two independent BHI360 raw XYZ frames; pressure and ToF protocols
remain backward compatible. No serial data are assumed valid when stale.
"""
from __future__ import annotations

import queue
import math
import re
import threading
from dataclasses import dataclass


@dataclass
class Reading:
    kind: str
    value: float | str | tuple[float, float, float]


def parse_line(line: str) -> Reading | None:
    s = line.strip().lstrip("# ").strip()
    if not s:
        return None
    if s.startswith("pressure,"):
        fields = dict(re.findall(r"([a-z_]+)=([^,\s]+)", s))
        if fields.get("valid") != "1":
            return None
        try:
            return Reading("pressure", int(fields["raw_adc"]))
        except (ValueError, KeyError):
            return None
    if s.startswith("tof,"):
        fields = dict(re.findall(r"([a-z_]+)=([^,\s]+)", s))
        if fields.get("valid") != "1" or fields.get("err") != "0":
            return None
        try:
            return Reading("tof", float(fields["raw_mm"]))
        except (ValueError, KeyError):
            return None
    if s.startswith(("IMU_", "DUAL_IMU_", "FOUR_")):
        return Reading("imu_status", s)
    if s.startswith("accel,"):
        fields = dict(re.findall(r"([a-z_]+)=([^,\\s]+)", s))
        role = fields.get("sensor")
        if fields.get("valid") != "1" or role not in ("head", "chest"):
            return None
        try:
            xyz = tuple(float(fields[k]) for k in ("x_raw", "y_raw", "z_raw"))
            if all(math.isfinite(value) for value in xyz):
                return Reading(f"{role}_accel", xyz)
        except (ValueError, KeyError):
            pass
        return None
    if s.startswith("imu,"):
        fields = dict(re.findall(r"([a-z_]+)=([^,\s]+)", s))
        if fields.get("valid", "1") != "1":
            return None
        try:
            deg = float(fields["head_pitch_deg"])
            if -180 <= deg <= 180:
                return Reading("head_pitch", deg)
        except (ValueError, KeyError):
            pass
    scan = re.match(r"SCAN_(START|FOUND|END) bus=(A2|B2)(?: address=(0x[0-9A-Fa-f]+))?", s)
    if scan:
        label, bus, address = scan.groups()
        return Reading("scan_" + label.lower(), bus + (":" + address if address else ""))
    if "# PRESSURE_FAULT" in line or "# PRESSURE_ABSENT" in line:
        return Reading("pressure_fault", s)
    return None


class SerialBridge:
    def __init__(self):
        self.events: queue.Queue[Reading] = queue.Queue(maxsize=300)
        self._stopping = threading.Event()
        self._thread: threading.Thread | None = None
        self.connected = False
        self._port = None

    def send(self, command: str) -> bool:
        """Only a single permitted v1 menu character, explicitly user-triggered."""
        if command not in ("c", "i", "s", "g", "m") or not self.connected or self._port is None:
            return False
        try:
            self._port.write((command + "\n").encode("ascii"))
            return True
        except Exception:
            return False

    def start(self, port: str):
        if self._thread and self._thread.is_alive():
            return
        self._stopping.clear()
        self._thread = threading.Thread(target=self._run, args=(port,), daemon=True)
        self._thread.start()

    def stop(self):
        self._stopping.set()

    def _emit(self, reading: Reading):
        try:
            self.events.put_nowait(reading)
        except queue.Full:
            try:
                self.events.get_nowait()
                self.events.put_nowait(reading)
            except queue.Empty:
                pass

    def _run(self, port: str):
        try:
            import serial  # pip install pyserial; not needed for virtual mode
            with serial.Serial(port, 115200, timeout=0.3) as conn:
                self._port = conn
                self.connected = True
                self._emit(Reading("connection", f"Connected to {port}"))
                while not self._stopping.is_set():
                    raw = conn.readline()
                    if not raw:
                        continue
                    reading = parse_line(raw.decode("utf-8", errors="replace"))
                    if reading:
                        self._emit(reading)
        except Exception as exc:
            self._emit(Reading("connection", f"Serial stopped: {exc}"))
        finally:
            self.connected = False
            self._port = None
