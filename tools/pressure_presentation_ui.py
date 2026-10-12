#!/usr/bin/env python3
"""K.E.V.I.N. presentation dashboard for the SAMD21 pressure-sensing PoC.

Live mode parses the existing 8-column CSV from feature/respiratory-slider-ui.
Demo mode generates unmistakably labeled simulated data without hardware.

This is a TRAINING PROTOTYPE, not a clinical ventilation measurement.
Positive/negative pressure do not establish inhaled/exhaled air volume.
"""

from __future__ import annotations

import argparse
import math
import threading
import time
import webbrowser
from dataclasses import asdict, dataclass
from typing import Optional

import serial
from serial.tools import list_ports
from flask import Flask, jsonify, render_template_string, request
from werkzeug.serving import make_server


@dataclass
class State:
    connected: bool = False
    port: str = ""
    raw: Optional[int] = None
    baseline: Optional[int] = None
    delta: Optional[int] = None
    t_ms: Optional[int] = None
    firmware_state: str = "DISCONNECTED"
    candidate_count: int = 0
    sample_ok: bool = False
    baseline_ok: bool = False
    last_positive_peak: Optional[int] = None
    last_negative_peak: Optional[int] = None
    last_event: str = "Waiting for SensorHub"
    last_comment: str = ""
    error: str = ""


class SerialPressureReader:
    def __init__(self, port: str, baud: int = 115200) -> None:
        self.port = port
        self.baud = baud
        self._lock = threading.Lock()
        self._state = State(port=port)
        self._serial: Optional[serial.Serial] = None
        self._last_received_monotonic = 0.0
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        """Stop serial collection and release COM port when exiting the dashboard."""
        self._stop_event.set()
        with self._lock:
            ser = self._serial
        if ser is not None:
            try:
                ser.close()
            except (serial.SerialException, OSError):
                pass
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def snapshot(self) -> dict:
        with self._lock:
            state = asdict(self._state)
            age = (time.monotonic() - self._last_received_monotonic
                   if self._last_received_monotonic else None)
        state["demo_mode"] = False
        state["sample_age_s"] = round(age, 2) if age is not None else None
        state["data_fresh"] = bool(state["connected"] and age is not None and age < 2.0)
        return state

    def recalibrate(self) -> bool:
        with self._lock:
            ser = self._serial
        if ser is None or not ser.is_open:
            return False
        try:
            ser.write(b"z")
            ser.flush()
            with self._lock:
                self._state.last_event = "Calibration requested — keep sensor still"
            return True
        except (serial.SerialException, OSError):
            return False

    @staticmethod
    def _field_from_comment(line: str, key: str) -> Optional[int]:
        token = key + "="
        if token not in line:
            return None
        try:
            return int(line.split(token, 1)[1].split(",", 1)[0].split(";", 1)[0].strip())
        except (IndexError, ValueError):
            return None

    def handle_line(self, line: str) -> None:
        """Parse one wire-protocol line; exposed for parser tests."""
        line = line.strip()
        if not line:
            return
        if line.startswith("#"):
            with self._lock:
                self._state.last_comment = line
                if line.startswith("# CANDIDATE_VENTILATION"):
                    self._state.last_positive_peak = self._field_from_comment(
                        line, "peak_delta_raw"
                    )
                    self._state.last_event = "Positive-pressure event recorded"
                elif line.startswith("# NEGATIVE_PRESSURE_END"):
                    peak = self._field_from_comment(line, "min_delta_raw")
                    self._state.last_negative_peak = abs(peak) if peak is not None else None
                    self._state.last_event = "Negative-pressure event recorded"
                elif line.startswith("# CALIBRATING"):
                    self._state.last_event = "Calibrating — keep sensor still"
                elif line.startswith("# READY"):
                    self._state.last_event = "Calibration complete — ready"
                elif line.startswith("# CALIBRATION_FAILED"):
                    self._state.last_event = "Calibration failed — retry at rest"
                elif line.startswith("# ADC_FAULT"):
                    self._state.last_event = "One ADC reading failed; check signal"
            return

        fields = line.split(",")
        if len(fields) != 8:
            return
        try:
            t_ms = int(fields[0])
            raw = int(fields[1]) if fields[1] else None
            baseline = int(fields[2]) if fields[2] else None
            delta = int(fields[3]) if fields[3] else None
            phase = fields[4]
            count = int(fields[5])
            sample_ok = fields[6] == "1"
            baseline_ok = fields[7] == "1"
            if fields[6] not in ("0", "1") or fields[7] not in ("0", "1"):
                return
        except ValueError:
            return

        with self._lock:
            self._last_received_monotonic = time.monotonic()
            self._state.connected = True
            self._state.t_ms = t_ms
            self._state.firmware_state = phase
            self._state.candidate_count = count
            self._state.sample_ok = sample_ok
            self._state.baseline_ok = baseline_ok
            # Never display a failed ADC sample as a new valid pressure reading.
            self._state.raw = raw if sample_ok else None
            self._state.baseline = baseline if baseline_ok else None
            self._state.delta = delta if sample_ok and baseline_ok else None
            self._state.error = ""

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                with serial.Serial(self.port, self.baud, timeout=0.8) as ser:
                    with self._lock:
                        self._serial = ser
                        self._state.connected = True
                        self._state.error = ""
                    while ser.is_open and not self._stop_event.is_set():
                        line = ser.readline()
                        if line:
                            self.handle_line(line.decode("utf-8", errors="replace"))
            except (OSError, serial.SerialException) as exc:
                with self._lock:
                    self._serial = None
                    self._state.connected = False
                    self._state.firmware_state = "DISCONNECTED"
                    self._state.error = str(exc)
                self._stop_event.wait(2)


class SimulatedPressureReader:
    """Clearly labeled synthetic pressure pattern, never presented as hardware."""
    def __init__(self) -> None:
        self._started = time.monotonic()

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def recalibrate(self) -> bool:
        return False

    def snapshot(self) -> dict:
        elapsed = time.monotonic() - self._started
        period = 9.0
        n = int(elapsed // period)
        phase = elapsed % period
        delta = 0
        state = "IDLE"
        event = "Pressure resting"
        if 1.5 <= phase < 3.2:
            delta = round(4900 * math.sin(math.pi * (phase - 1.5) / 1.7))
            state = "POSITIVE_EVENT"
            event = "Positive pressure — simulated push"
        elif 4.2 <= phase < 5.7:
            delta = -round(3100 * math.sin(math.pi * (phase - 4.2) / 1.5))
            state = "NEGATIVE_EVENT"
            event = "Negative pressure — simulated pull"

        return {
            **asdict(State(
                connected=True, port="SIMULATED",
                raw=2520 + delta, baseline=2520, delta=delta,
                t_ms=int(elapsed * 1000), firmware_state=state,
                candidate_count=n + int(phase >= 3.2),
                sample_ok=True, baseline_ok=True,
                last_positive_peak=4900 if elapsed >= 3.2 else None,
                last_negative_peak=3100 if elapsed >= 5.7 else None,
                last_event=event, last_comment="# SIMULATED DATA — NOT A SENSOR"
            )),
            "demo_mode": True,
            "data_fresh": True,
            "sample_age_s": 0.0
        }


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>K.E.V.I.N. | Respiratory Sensor Demonstration</title>
<style>
:root{color-scheme:dark;--bg:#080f1c;--surface:#121f31;--surface2:#18283c;--line:#293c52;--text:#f6fbff;--muted:#a9bbce;--mint:#63e6bc;--blue:#6db8ff;--amber:#ffc979;--danger:#ff8087}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 72% -10%,#152f4a,transparent 56%),var(--bg);color:var(--text);font-family:Inter,"Segoe UI",system-ui,sans-serif}
.wrapper{max-width:1250px;margin:auto;padding:26px 28px 34px}
header{display:flex;align-items:center;justify-content:space-between;gap:20px;padding-bottom:22px;border-bottom:1px solid var(--line)}
.wordmark{font-weight:900;letter-spacing:.10em;font-size:27px}.wordmark span{color:var(--mint)}.eyebrow{font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:var(--muted);margin:4px 0 0}
.source{border:1px solid var(--line);border-radius:100px;padding:10px 16px;font-weight:750;font-size:13px;background:#172639}
.source.demo{color:var(--amber);background:#50371e;border-color:#a47843}
.hero{display:flex;align-items:center;justify-content:space-between;gap:24px;padding:26px 0 20px;flex-wrap:wrap}
h1{font-size:clamp(28px,3vw,40px);letter-spacing:-.035em;line-height:1.13;margin:0 0 8px}.subtitle{color:var(--muted);font-size:15px;margin:0;max-width:770px}
.controls{display:flex;gap:10px;flex-wrap:wrap}
button{background:#d6faf0;color:#102c28;border:0;padding:12px 18px;border-radius:10px;font-weight:800;font-size:14px;cursor:pointer}
button:disabled{opacity:.5;cursor:not-allowed}
button.secondary{color:#e4f3ff;background:#20334b;border:1px solid #36516a}
.health{display:grid;grid-template-columns:2fr 1fr;gap:16px;margin:0 0 16px}
.banner,.card{background:linear-gradient(150deg,#16263b,#101d2e);border:1px solid var(--line);border-radius:18px}
.banner{display:flex;align-items:center;padding:18px 22px;gap:16px;min-height:91px}
.led{width:22px;height:22px;flex-shrink:0;border-radius:100%;background:#627287;box-shadow:0 0 0 7px #64778d21}
.led.ready{background:var(--mint);box-shadow:0 0 0 7px #63e6bc24,0 0 25px #63e6bc44}
.led.active{background:var(--blue);box-shadow:0 0 0 7px #6db8ff2c,0 0 30px #6db8ff77}
.led.warn{background:var(--amber);box-shadow:0 0 0 7px #ffc97929}
.led.error{background:var(--danger);box-shadow:0 0 0 7px #ff80872b}
.banner b{font-size:21px}.banner p{margin:3px 0 0;color:var(--muted);font-size:14px}
.quickstat{text-align:right;justify-content:space-between}.quickstat .big{font-size:32px;font-weight:900;line-height:1}.quickstat .label{font-size:13px;color:var(--muted);padding-left:12px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.card{padding:23px}
.measure{position:relative;overflow:hidden;transition:border-color .2s,background .2s}.measure.positive.live{border-color:#3aab9b;background:linear-gradient(150deg,#173a3b,#111e2e)}
.measure.negative.live{border-color:#447ba9;background:linear-gradient(150deg,#1a3353,#111e2e)}
.cardhead{display:flex;justify-content:space-between;gap:10px;align-items:center}
.direction{font-weight:850;font-size:22px;letter-spacing:-.02em}
.description{font-size:13px;color:var(--muted);margin-top:5px}
.live-led{width:13px;height:13px;border-radius:100%;background:#4c6074;box-shadow:none;transition:.18s}
.positive.live .live-led{background:var(--mint);box-shadow:0 0 20px 5px #63e6bc66}
.negative.live .live-led{background:var(--blue);box-shadow:0 0 20px 5px #6db8ff66}
.measurement{display:flex;align-items:baseline;gap:10px;margin:26px 0 17px;font-variant-numeric:tabular-nums}
.measurement .number{font-size:clamp(40px,5vw,64px);font-weight:900;letter-spacing:-.05em;line-height:1}
.measurement .unit{color:var(--muted);font-weight:700;font-size:14px}
.track{height:18px;border-radius:12px;background:#304057;overflow:hidden}
.fill{width:0%;height:100%;background:linear-gradient(90deg,#258c80,var(--mint));border-radius:12px;transition:width .12s}
.negative .fill{background:linear-gradient(90deg,#285ca1,var(--blue))}
.foot{display:flex;justify-content:space-between;color:var(--muted);font-size:12px;margin-top:11px;gap:10px}
.wavecard{margin-top:16px;padding:23px}
.wavehead{display:flex;justify-content:space-between;align-items:center;gap:15px;flex-wrap:wrap}
h2{margin:0;font-size:19px}.muted{color:var(--muted);font-size:13px}
select{background:#213349;color:var(--text);border:1px solid #3b5772;border-radius:8px;padding:7px 12px;font:inherit}
canvas{display:block;width:100%;height:220px;margin-top:16px}
.summary{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:16px}
.summary .value{font-weight:850;font-size:23px;margin-top:10px;font-variant-numeric:tabular-nums}
.section-label{font-size:12px;text-transform:uppercase;letter-spacing:.12em;color:var(--muted)}
details{margin-top:16px;border-radius:14px;border:1px solid var(--line);background:var(--surface)}
summary{padding:17px 20px;cursor:pointer;font-weight:800}
.technical{padding:4px 20px 20px;display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
.kv{border-radius:10px;background:#1b2b40;padding:15px;min-width:0}
.kv strong{display:block;font-variant-numeric:tabular-nums;font-size:19px;margin-top:9px;overflow-wrap:anywhere}
.note{font-size:13px;line-height:1.55;color:var(--muted);margin:18px 0 0}
.mode-warning{background:#4a311e;border:1px solid #c38944;color:#ffe0aa;padding:12px 16px;border-radius:10px;margin-top:14px;font-size:14px}
.hidden{display:none}
@media(max-width:780px){.wrapper{padding:18px}.health,.grid{grid-template-columns:1fr}.summary{grid-template-columns:repeat(2,1fr)}.technical{grid-template-columns:repeat(2,1fr)}.quickstat{text-align:left}}
@media(max-width:470px){.summary,.technical{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="wrapper">
  <header>
    <div>
      <div class="wordmark">K<span>.</span>E<span>.</span>V<span>.</span>I<span>.</span>N<span>.</span></div>
      <p class="eyebrow">Infant resuscitation training · pressure sensor prototype</p>
    </div>
    <div class="source" id="sourceBadge">CONNECTING TO SENSOR</div>
  </header>
  <div class="hero">
    <div><h1>See the pressure change.</h1><p class="subtitle">Apply and release gentle pressure at the test sensor. Watch the direction, live response and recorded events.</p></div>
    <div class="controls">
      <button id="calibrate" onclick="calibrate()">Calibrate sensor</button>
      <button class="secondary" onclick="clearGraph()">Clear graph</button>
      <button class="secondary" onclick="toggleFullscreen()">Full screen</button>
      <button class="secondary" id="stopButton" onclick="stopDashboard()">Stop dashboard</button>
    </div>
  </div>
  <div class="health">
    <div class="banner" role="status" aria-live="polite">
      <span id="led" class="led"></span>
      <div><b id="mainStatus">Waiting for SensorHub</b><p id="mainHelp">Connect the SAMD21 with a USB data cable.</p></div>
    </div>
    <div class="banner quickstat">
      <div><div class="big" id="eventCount">0</div><div class="label">new positive-pressure events this session</div></div>
    </div>
  </div>
  <main class="grid">
    <section class="card measure positive" id="positiveCard">
      <div class="cardhead"><div><div class="direction">Pressure increases</div><div class="description">Positive pressure · pressing the syringe</div></div><span class="live-led" aria-hidden="true"></span></div>
      <div class="measurement"><span class="number" id="positiveNumber">0</span><span class="unit">raw ADC counts</span></div>
      <div class="track"><div class="fill" id="positiveFill"></div></div>
      <div class="foot"><span>Rest</span><span id="positiveScale">Display full scale: 8,000</span></div>
    </section>
    <section class="card measure negative" id="negativeCard">
      <div class="cardhead"><div><div class="direction">Pressure decreases</div><div class="description">Negative pressure · pulling the syringe</div></div><span class="live-led" aria-hidden="true"></span></div>
      <div class="measurement"><span class="number" id="negativeNumber">0</span><span class="unit">raw ADC counts</span></div>
      <div class="track"><div class="fill" id="negativeFill"></div></div>
      <div class="foot"><span>Rest</span><span id="negativeScale">Display full scale: 8,000</span></div>
    </section>
  </main>
  <section class="card wavecard">
    <div class="wavehead"><div><h2>Live pressure waveform</h2><div class="muted">Last 25 seconds · zero is the resting baseline</div></div>
      <label class="muted">Visual scale
        <select id="scale" onchange="setScale(this.value)">
          <option value="2000">±2,000</option>
          <option value="8000" selected>±8,000</option>
          <option value="16000">±16,000</option>
          <option value="32000">±32,000</option>
        </select>
      </label>
    </div>
    <canvas id="wave" aria-label="Live graph of positive and negative raw pressure deviations"></canvas>
    <div class="muted">This scale changes the display only. It does not change sensor sensitivity or the firmware's detection threshold.</div>
  </section>
  <section class="summary">
    <div class="card"><div class="section-label">Current activity</div><div class="value" id="activity">Waiting</div></div>
    <div class="card"><div class="section-label">Last positive event peak</div><div class="value" id="lastPositive">—</div></div>
    <div class="card"><div class="section-label">Last negative event peak</div><div class="value" id="lastNegative">—</div></div>
  </section>
  <details>
    <summary>Engineering details · sensor and firmware <span class="muted">(click to expand)</span></summary>
    <div class="technical">
      <div class="kv"><div class="section-label">Device / COM port</div><strong id="port">—</strong></div>
      <div class="kv"><div class="section-label">Firmware state</div><strong id="fwState">—</strong></div>
      <div class="kv"><div class="section-label">Raw ADC</div><strong id="raw">—</strong></div>
      <div class="kv"><div class="section-label">Calibrated baseline (raw)</div><strong id="baseline">—</strong></div>
      <div class="kv"><div class="section-label">Signed ADC delta</div><strong id="delta">—</strong></div>
      <div class="kv"><div class="section-label">ADC sample valid</div><strong id="sampleOk">—</strong></div>
      <div class="kv"><div class="section-label">Baseline valid</div><strong id="baselineOk">—</strong></div>
      <div class="kv"><div class="section-label">Last data age</div><strong id="age">—</strong></div>
    </div>
    <p class="note" style="padding:0 20px 20px;margin:0">Sensor chain: MPXV5010GP → MCP3426 ADC (I²C address 0x68) → SAMD21 SensorHub → USB serial (115200 baud) → Python/Flask dashboard. Event trigger ±200 raw counts and return band ±80 counts are experimental settings, not clinical thresholds. No airflow, delivered volume or calibrated airway pressure is measured.</p>
  </details>
  <div id="demoWarning" class="mode-warning hidden">SIMULATION MODE — this display uses generated sample data, not a connected pressure sensor. Do not present these readings as measurements.</div>
  <p class="note">Research/demo prototype only. The positive and negative readings describe pressure changes at the sensor; they do <strong>not</strong> prove that a baby inhaled or exhaled, how much air was delivered, or whether resuscitation was effective.</p>
</div>
<script>
const SCALE_DEFAULT={{ display_max }};
const graph=[];
const horizon=25000;
let displayScale=SCALE_DEFAULT;
let lastTimestamp=null;
let calibrateCooldown=false;
let dashboardStopped=false;
let eventCounterStart=null;
let previousEventCount=null;
const $ = id => document.getElementById(id);
const fmt = v => v === null || v === undefined ? "—" : Number(v).toLocaleString("en-US");
const setText=(id,value)=>{$(id).textContent=value;};

function setScale(v){
  displayScale=Math.max(100,Number(v));
  setText("positiveScale","Display full scale: "+fmt(displayScale));
  setText("negativeScale","Display full scale: "+fmt(displayScale));
  renderGraph();
}
function clearGraph(){graph.length=0;lastTimestamp=null;renderGraph();}
function toggleFullscreen(){
  if(document.fullscreenElement){document.exitFullscreen();}
  else if(document.documentElement.requestFullscreen){document.documentElement.requestFullscreen();}
}
function paintCard(id,fill,value,active){
  $(id).classList.toggle("live",active);
  $(fill).style.width=(Math.min(100,Math.max(0,100*value/displayScale)))+"%";
}
function addPoint(s) {
  if(s.t_ms === null || s.t_ms === undefined || s.delta === null || !s.sample_ok || !s.baseline_ok || !s.data_fresh) return;
  if(lastTimestamp !== null && s.t_ms < lastTimestamp){clearGraph();}
  if(s.t_ms === lastTimestamp)return;
  lastTimestamp=s.t_ms;
  graph.push({t:Date.now(),y:s.delta});
  const oldest=Date.now()-horizon;
  while(graph.length && graph[0].t < oldest)graph.shift();
}
function renderGraph(){
  const canvas=$("wave");
  const rect=canvas.getBoundingClientRect();
  const dpr=window.devicePixelRatio||1;
  const w=Math.max(1,rect.width),h=Math.max(1,rect.height);
  if(canvas.width !== Math.round(w*dpr)||canvas.height !== Math.round(h*dpr)){
    canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);
  }
  const ctx=canvas.getContext("2d");ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);
  const pad=10,baseY=h/2,range=(h/2)-pad;
  ctx.strokeStyle="#294058";ctx.lineWidth=1;
  for(let k=-2;k<=2;k++){
    const y=baseY + k*(range/2);
    ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(w,y);ctx.stroke();
  }
  ctx.fillStyle="#a9bbce";ctx.font="12px Segoe UI, sans-serif";
  ctx.fillText("+",4,13);ctx.fillText("0",4,baseY-6);ctx.fillText("−",4,h-8);
  if(graph.length<2)return;
  const now=Date.now();
  for(let sign of [1,-1]){
    ctx.strokeStyle=sign>0?"#63e6bc":"#6db8ff";ctx.lineWidth=2.8;
    ctx.beginPath();let started=false;
    for(const p of graph){
      const value=sign>0?Math.max(0,p.y):Math.min(0,p.y);
      const x=w-(now-p.t)/horizon*w;
      const y=baseY - value/displayScale*range;
      const yy=Math.max(pad,Math.min(h-pad,y));
      if(!started){ctx.moveTo(x,yy);started=true;}else ctx.lineTo(x,yy);
    }
    ctx.stroke();
  }
}
function updateUI(s){
  const simulated=Boolean(s.demo_mode);
  $("sourceBadge").classList.toggle("demo",simulated);
  setText("sourceBadge",simulated?"SIMULATED DEMO · NO SENSOR":s.connected?"LIVE SENSOR · "+s.port:"SENSOR NOT CONNECTED");
  $("demoWarning").classList.toggle("hidden",!simulated);
  $("calibrate").disabled=simulated||calibrateCooldown||!s.connected;

  let title,help,led="warn", activity="Waiting";
  if(!s.connected){title="Sensor disconnected";help="Check USB cable and close other serial monitors.";led="error";}
  else if(!s.data_fresh){title="Waiting for sensor data";help="Connected to serial, but no recent measurements are arriving.";led="warn";}
  else if(s.firmware_state==="CALIBRATING"){title="Calibrating sensor";help="Keep the syringe/pressure port at rest.";led="warn";}
  else if(!s.baseline_ok){title="Calibration needed";help="Keep pressure at rest and click Calibrate sensor once.";led="warn";}
  else if(!s.sample_ok){title="Sensor read interrupted";help="Waiting for the next valid reading; calibration is retained.";led="warn";}
  else if(s.firmware_state==="POSITIVE_EVENT"){title="Positive pressure detected";help="The sensor detects rising pressure.";led="active";activity="Positive pressure";}
  else if(s.firmware_state==="NEGATIVE_EVENT"){title="Negative pressure detected";help="The sensor detects falling pressure.";led="active";activity="Negative pressure";}
  else{title="Sensor ready";help="Calibrated baseline retained. Apply pressure to see the response.";led="ready";activity="At rest";}
  setText("mainStatus",title);
  setText("mainHelp",help);
  $("led").className="led "+led;
  setText("activity",activity);
  // The SAMD21's lifetime count persists across dashboard sessions.
  // Show only new events since this browser page was opened.
  if(eventCounterStart===null || (previousEventCount!==null && s.candidate_count<previousEventCount)){
    eventCounterStart=s.candidate_count;
  }
  previousEventCount=s.candidate_count;
  setText("eventCount",fmt(Math.max(0,s.candidate_count-eventCounterStart)));
  setText("lastPositive",s.last_positive_peak === null?"—":"+"+fmt(s.last_positive_peak));
  setText("lastNegative",s.last_negative_peak === null?"—":"−"+fmt(s.last_negative_peak));

  const valid=s.connected&&s.data_fresh&&s.baseline_ok&&s.sample_ok&&s.delta!==null;
  const positive=valid?Math.max(0,s.delta):0;
  const negative=valid?Math.max(0,-s.delta):0;
  setText("positiveNumber",fmt(positive));
  setText("negativeNumber",fmt(negative));
  paintCard("positiveCard","positiveFill",positive,valid&&positive>200);
  paintCard("negativeCard","negativeFill",negative,valid&&negative>200);

  setText("port",s.port||"—");setText("fwState",s.firmware_state||"—");
  setText("raw",fmt(s.raw));setText("baseline",fmt(s.baseline));
  setText("delta",s.delta===null?"—":(s.delta>0?"+":"")+fmt(s.delta));
  setText("sampleOk",s.sample_ok?"YES":"NO");
  setText("baselineOk",s.baseline_ok?"YES":"NO");
  setText("age",s.sample_age_s===null?"—":s.sample_age_s+" s");
  addPoint(s);renderGraph();
}
async function poll(){
  if(dashboardStopped)return;
  try{
    const response=await fetch("/api/state",{cache:"no-store"});
    if(!response.ok)throw new Error("HTTP "+response.status);
    updateUI(await response.json());
  }catch(error){
    setText("mainStatus","Dashboard connection interrupted");
    setText("mainHelp","Check the Python terminal: "+error.message);
    $("led").className="led error";
  }
}
async function calibrate(){
  if(calibrateCooldown)return;
  calibrateCooldown=true;
  $("calibrate").disabled=true;
  setText("mainStatus","Calibration requested");
  setText("mainHelp","Keep the syringe/pressure port at rest.");
  try{
    const response=await fetch("/api/recalibrate",{method:"POST"});
    const result=await response.json();
    if(!result.ok)alert(result.message);
  }catch(error){alert("Unable to send calibration command: "+error.message);}
  window.setTimeout(()=>{calibrateCooldown=false;},5500);
}
async function stopDashboard(){
  if(dashboardStopped)return;
  if(!window.confirm("Stop the K.E.V.I.N. dashboard and release the sensor COM port?"))return;
  $("stopButton").disabled=true;
  try{
    const response=await fetch("/api/stop",{method:"POST"});
    const result=await response.json();
    if(!response.ok || !result.ok)throw new Error(result.message || "Could not stop");
    dashboardStopped=true;
    setText("mainStatus","Dashboard stopped");
    setText("mainHelp","The COM port has been released. You can close this tab.");
    setText("sourceBadge","SERVER STOPPED");
    $("led").className="led";
    $("calibrate").disabled=true;
    setText("stopButton","Stopped");
  }catch(error){
    $("stopButton").disabled=false;
    alert("Could not stop the dashboard: "+error.message);
  }
}
$("scale").value=String(SCALE_DEFAULT);
if($("scale").value!==String(SCALE_DEFAULT)){$("scale").value="8000";}
setScale($("scale").value);
window.addEventListener("resize",renderGraph);
window.setInterval(poll,160);
window.setInterval(renderGraph,500);
poll();
</script>
</body>
</html>
"""


def create_app(reader, display_max: int = 8000, stop_callback=None) -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index():
        return render_template_string(PAGE, display_max=display_max)

    @app.get("/api/state")
    def state():
        return jsonify(reader.snapshot())

    @app.post("/api/recalibrate")
    def calibrate():
        if reader.recalibrate():
            return jsonify(ok=True, message="Calibration command sent")
        return jsonify(ok=False, message="Sensor not connected or running in simulated demo mode"), 503

    @app.post("/api/stop")
    def stop_dashboard():
        # Only allow the locally served app to request process shutdown.
        # This also prevents a cross-site HTML form from stopping a running demo.
        origin = request.headers.get("Origin", "")
        if origin != request.host_url.rstrip("/"):
            return jsonify(ok=False, message="Stop must be requested by this dashboard"), 403
        if stop_callback is None:
            return jsonify(ok=False, message="Dashboard stop is unavailable"), 503
        threading.Thread(target=stop_callback, daemon=True).start()
        return jsonify(ok=True, message="Stopping dashboard and releasing COM port")

    return app


def find_sensorhub_port() -> Optional[str]:
    """Discover the proven SensorHub application-mode VID:PID, not bootloader."""
    matches = sorted(
        p.device for p in list_ports.comports()
        if p.vid == 0x239A and p.pid == 0x801B
    )
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print("Multiple SensorHub-like devices found:", ", ".join(matches))
        print("Use --serial-port COMx to select a specific device.")
        return None
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="K.E.V.I.N. pressure presentation dashboard")
    parser.add_argument("--serial-port", default="auto",
                        help="COM3 or /dev/ttyACM0; default auto-detects SensorHub 239A:801B")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--host", default="127.0.0.1",
                        help="Loopback by default; use 0.0.0.0 only if LAN access is needed")
    parser.add_argument("--web-port", type=int, default=5000)
    parser.add_argument("--display-max", type=int, choices=[2000, 8000, 16000, 32000],
                        default=8000, help="Visual scale only; does not affect sensor or firmware")
    parser.add_argument("--demo", action="store_true",
                        help="Run clearly labeled simulated pressure patterns without hardware")
    parser.add_argument("--open-browser", action="store_true",
                        help="Open the dashboard in the default browser automatically")
    args = parser.parse_args()

    if args.demo:
        reader = SimulatedPressureReader()
    else:
        selected = find_sensorhub_port() if args.serial_port.lower() == "auto" else args.serial_port
        if selected is None:
            print("SensorHub application USB device (VID:PID 239A:801B) not found.")
            print("Connect the SAMD21 or specify --serial-port COM3.")
            print("Or use --demo for an explicitly labeled simulated presentation.")
            raise SystemExit(2)
        reader = SerialPressureReader(selected, args.baud)

    server_ref = {"server": None}

    def shutdown():
        current = server_ref["server"]
        if current is not None:
            current.shutdown()

    app = create_app(reader, args.display_max, stop_callback=shutdown)
    try:
        server = make_server(args.host, args.web_port, app, threaded=True)
        server_ref["server"] = server
    except OSError as exc:
        print("Could not start local dashboard on port %d: %s" % (args.web_port, exc))
        print("Is another copy of the dashboard still running?")
        raise SystemExit(1)

    reader.start()

    print("K.E.V.I.N. pressure dashboard: "+("SIMULATED DEMO" if args.demo else "LIVE SENSOR"))
    url = "http://127.0.0.1:%d" % args.web_port
    print("Open "+url)
    if args.open_browser:
        threading.Thread(target=lambda: webbrowser.open(url), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        reader.stop()
        server.server_close()
        print("Dashboard stopped; serial port released.")


if __name__ == "__main__":
    main()
