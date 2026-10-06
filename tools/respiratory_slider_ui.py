#!/usr/bin/env python3
"""
K.E.V.I.N. respiratory pressure slider UI.

Reads the CSV stream produced by the SAMD21 pressure logger and serves a
browser-based interface with separate live sliders for positive-pressure
("inhale") and negative-pressure ("exhale") activity.

Important:
- The values are RAW ADC delta counts, not calibrated pressure.
- Positive/negative pressure events are not yet validated clinical breaths.
- Pressure alone cannot determine delivered ventilation volume.
"""

from __future__ import annotations

import argparse
import threading
import time
from dataclasses import asdict, dataclass
from typing import Optional

import serial
from flask import Flask, jsonify, render_template_string


@dataclass
class DashboardState:
    connected: bool = False
    port: str = ""
    t_ms: Optional[int] = None
    raw: Optional[int] = None
    baseline: Optional[int] = None
    delta: Optional[int] = None
    pressure_state: str = "DISCONNECTED"
    candidate_count: int = 0
    sample_ok: bool = False
    baseline_ok: bool = False
    inhale_delta: int = 0
    exhale_delta: int = 0
    last_positive_peak: Optional[int] = None
    last_negative_peak: Optional[int] = None
    last_event: str = "No event yet"
    last_comment: str = ""
    error: str = ""


class PressureSerialReader:
    def __init__(self, port: str, baud: int = 115200):
        self.port = port
        self.baud = baud
        self._lock = threading.Lock()
        self._state = DashboardState(port=port)
        self._serial: Optional[serial.Serial] = None
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def snapshot(self) -> DashboardState:
        with self._lock:
            return DashboardState(**asdict(self._state))

    def recalibrate(self) -> bool:
        with self._lock:
            ser = self._serial
        if ser is None or not ser.is_open:
            return False
        try:
            ser.write(b"z")
            ser.flush()
            return True
        except serial.SerialException:
            return False

    def _set_disconnected(self, error: str) -> None:
        with self._lock:
            self._state.connected = False
            self._state.pressure_state = "DISCONNECTED"
            self._state.inhale_delta = 0
            self._state.exhale_delta = 0
            self._state.error = error
            self._serial = None

    @staticmethod
    def _extract_int(text: str, key: str) -> Optional[int]:
        marker = key + "="
        if marker not in text:
            return None
        try:
            value = text.split(marker, 1)[1].split(",", 1)[0].split(";", 1)[0].strip()
            return int(value)
        except (ValueError, IndexError):
            return None

    def _handle_comment(self, line: str) -> None:
        with self._lock:
            self._state.last_comment = line

            if line.startswith("# CANDIDATE_VENTILATION"):
                peak = self._extract_int(line, "peak_delta_raw")
                if peak is not None:
                    self._state.last_positive_peak = peak
                self._state.last_event = "Positive-pressure event completed"

            elif line.startswith("# NEGATIVE_PRESSURE_END"):
                minimum = self._extract_int(line, "min_delta_raw")
                if minimum is not None:
                    self._state.last_negative_peak = abs(minimum)
                self._state.last_event = "Negative-pressure event completed"

            elif line.startswith("# CALIBRATING"):
                self._state.last_event = "Calibrating baseline"

            elif line.startswith("# READY"):
                self._state.last_event = "Baseline ready"

            elif "CALIBRATION_FAILED" in line or "ADC_FAULT" in line:
                self._state.last_event = "Sensor/calibration fault"

    def _handle_sample(self, line: str) -> None:
        parts = line.split(",")
        if len(parts) != 8:
            return

        try:
            t_ms = int(parts[0]) if parts[0] else None
            raw = int(parts[1]) if parts[1] else None
            baseline = int(parts[2]) if parts[2] else None
            delta = int(parts[3]) if parts[3] else None
            state_name = parts[4] or "UNKNOWN"
            candidate_count = int(parts[5]) if parts[5] else 0
            sample_ok = parts[6] == "1"
            baseline_ok = parts[7] == "1"
        except ValueError:
            return

        inhale_delta = max(delta or 0, 0)
        exhale_delta = max(-(delta or 0), 0)

        with self._lock:
            self._state.connected = True
            self._state.t_ms = t_ms
            self._state.raw = raw
            self._state.baseline = baseline
            self._state.delta = delta
            self._state.pressure_state = state_name
            self._state.candidate_count = candidate_count
            self._state.sample_ok = sample_ok
            self._state.baseline_ok = baseline_ok
            self._state.inhale_delta = inhale_delta
            self._state.exhale_delta = exhale_delta
            self._state.error = ""

    def _run(self) -> None:
        while True:
            try:
                ser = serial.Serial(self.port, self.baud, timeout=1)
                with self._lock:
                    self._serial = ser
                    self._state.connected = True
                    self._state.error = ""

                while ser.is_open:
                    data = ser.readline()
                    if not data:
                        continue

                    line = data.decode("utf-8", errors="ignore").strip()
                    if not line:
                        continue

                    if line.startswith("#"):
                        self._handle_comment(line)
                    else:
                        self._handle_sample(line)

            except (serial.SerialException, OSError) as exc:
                self._set_disconnected(str(exc))
                time.sleep(2)


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>K.E.V.I.N. Respiratory Pressure UI</title>
<style>
  :root {
    font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }
  body {
    margin: 0;
    background: #111827;
    color: #f9fafb;
  }
  .wrap {
    max-width: 980px;
    margin: 0 auto;
    padding: 28px;
  }
  h1 { margin-bottom: 4px; }
  .subtitle { color: #9ca3af; margin-top: 0; }
  .grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 18px;
    margin-top: 24px;
  }
  .card {
    background: #1f2937;
    border: 1px solid #374151;
    border-radius: 16px;
    padding: 22px;
  }
  .card h2 { margin-top: 0; }
  .value {
    font-size: 2.2rem;
    font-weight: 700;
    margin: 12px 0 4px;
  }
  input[type="range"] {
    width: 100%;
    height: 42px;
  }
  #inhaleSlider { accent-color: #22c55e; }
  #exhaleSlider { accent-color: #60a5fa; }
  .meta {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
    margin-top: 18px;
  }
  .meta .card { padding: 16px; }
  .label { color: #9ca3af; font-size: .9rem; }
  .small { font-size: .9rem; color: #d1d5db; }
  .warning {
    margin-top: 20px;
    padding: 14px 16px;
    background: #422006;
    border: 1px solid #92400e;
    border-radius: 12px;
    color: #fde68a;
  }
  button {
    padding: 10px 16px;
    border: 0;
    border-radius: 10px;
    font-weight: 700;
    cursor: pointer;
  }
  .status-row {
    display: flex;
    gap: 14px;
    align-items: center;
    flex-wrap: wrap;
    margin-top: 16px;
  }
  .badge {
    padding: 6px 10px;
    border-radius: 999px;
    background: #374151;
  }
  @media (max-width: 700px) {
    .grid, .meta { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>
<div class="wrap">
  <h1>K.E.V.I.N. Respiratory Pressure</h1>
  <p class="subtitle">Live proof-of-concept pressure display from the SensorHub</p>

  <div class="status-row">
    <span class="badge" id="connection">Connecting...</span>
    <span class="badge">State: <strong id="pressureState">—</strong></span>
    <span class="badge">Candidate count: <strong id="candidateCount">0</strong></span>
    <button onclick="recalibrate()">Recalibrate baseline</button>
  </div>

  <div class="grid">
    <section class="card">
      <h2>Inhale / positive pressure</h2>
      <div class="value">+<span id="inhaleValue">0</span> raw</div>
      <input id="inhaleSlider" type="range" min="0" max="{{ display_max }}" value="0" disabled>
      <p class="small">Last positive-event peak: <strong id="positivePeak">—</strong></p>
    </section>

    <section class="card">
      <h2>Exhale / negative pressure</h2>
      <div class="value">−<span id="exhaleValue">0</span> raw</div>
      <input id="exhaleSlider" type="range" min="0" max="{{ display_max }}" value="0" disabled>
      <p class="small">Last negative-event magnitude: <strong id="negativePeak">—</strong></p>
    </section>
  </div>

  <div class="meta">
    <div class="card"><div class="label">Current delta</div><strong id="delta">—</strong></div>
    <div class="card"><div class="label">Baseline</div><strong id="baseline">—</strong></div>
    <div class="card"><div class="label">Raw ADC</div><strong id="raw">—</strong></div>
  </div>

  <div class="card" style="margin-top:18px">
    <div class="label">Last event / status</div>
    <strong id="lastEvent">Waiting for data...</strong>
    <div class="small" id="error" style="margin-top:8px"></div>
  </div>

  <div class="warning">
    These sliders display uncalibrated raw ADC differences. They are not clinical
    airway-pressure or tidal-volume measurements, and positive/negative events are
    not yet validated infant inhale/exhale events.
  </div>
</div>

<script>
const displayMax = {{ display_max }};

function textOrDash(value) {
  return value === null || value === undefined ? "—" : value;
}

async function updateState() {
  try {
    const response = await fetch("/api/state", {cache: "no-store"});
    const s = await response.json();

    document.getElementById("connection").textContent =
      s.connected ? "Serial connected: " + s.port : "Serial disconnected";

    document.getElementById("pressureState").textContent = s.pressure_state;
    document.getElementById("candidateCount").textContent = s.candidate_count;
    document.getElementById("delta").textContent = textOrDash(s.delta);
    document.getElementById("baseline").textContent = textOrDash(s.baseline);
    document.getElementById("raw").textContent = textOrDash(s.raw);
    document.getElementById("lastEvent").textContent = s.last_event;
    document.getElementById("error").textContent = s.error || "";

    const inhale = Math.min(s.inhale_delta || 0, displayMax);
    const exhale = Math.min(s.exhale_delta || 0, displayMax);

    document.getElementById("inhaleSlider").value = inhale;
    document.getElementById("exhaleSlider").value = exhale;
    document.getElementById("inhaleValue").textContent = s.inhale_delta || 0;
    document.getElementById("exhaleValue").textContent = s.exhale_delta || 0;

    document.getElementById("positivePeak").textContent =
      textOrDash(s.last_positive_peak);
    document.getElementById("negativePeak").textContent =
      textOrDash(s.last_negative_peak);
  } catch (err) {
    document.getElementById("connection").textContent = "Dashboard connection error";
  }
}

async function recalibrate() {
  const response = await fetch("/api/recalibrate", {method: "POST"});
  const result = await response.json();
  if (!result.ok) {
    alert(result.message);
  }
}

setInterval(updateState, 150);
updateState();
</script>
</body>
</html>
"""


def create_app(reader: PressureSerialReader, display_max: int) -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index():
        return render_template_string(PAGE, display_max=display_max)

    @app.get("/api/state")
    def api_state():
        state = asdict(reader.snapshot())
        state["display_max"] = display_max
        return jsonify(state)

    @app.post("/api/recalibrate")
    def api_recalibrate():
        if reader.recalibrate():
            return jsonify(ok=True, message="Recalibration command sent.")
        return jsonify(ok=False, message="Serial device is not connected."), 503

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="K.E.V.I.N. respiratory pressure slider UI")
    parser.add_argument("--serial-port", default="/dev/ttyACM0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--web-port", type=int, default=5000)
    parser.add_argument(
        "--display-max",
        type=int,
        default=4000,
        help="Maximum raw delta shown by each slider; values above this are clipped visually.",
    )
    args = parser.parse_args()

    reader = PressureSerialReader(args.serial_port, args.baud)
    reader.start()

    app = create_app(reader, args.display_max)
    app.run(host=args.host, port=args.web_port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
