"""K.E.V.I.N. interactive infant patient-monitor training demo.

Launch: py -3 app.py  (Windows). Tkinter is part of standard Python installs.
Hardware inputs: py -3 -m pip install pyserial, after stopping PlatformIO monitor.
"""
from __future__ import annotations

from collections import deque
import math
import time
import tkinter as tk
from tkinter import ttk, messagebox

from engine import PatientEngine, PressureBreathDetector, Settings, ToFCompressionDetector
from serial_bridge import SerialBridge

BG = "#080f1a"
PANEL = "#101d2c"
CARD = "#142436"
INK = "#f2f6fc"
MUTED = "#91a6be"
GREEN = "#3ef2a0"
BLUE = "#43c8fa"
YELLOW = "#ffc96a"
RED = "#ff7286"


class MonitorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("K.E.V.I.N. | Infant Patient Monitor — TRAINING ONLY")
        self.configure(bg=BG)
        self.geometry("1280x850")
        self.minsize(1040, 740)

        self.model = PatientEngine()
        self.pressure = PressureBreathDetector()
        self.tof = ToFCompressionDetector()
        self.serial = SerialBridge()
        self.last_wall = time.monotonic()
        self.last_pressure_wall = -1e6
        self.last_tof_wall = -1e6
        self.last_imu_wall = -1e6
        self.next_mock_breath = 0.0
        self.mock_tof_last: float | None = None
        self.last_reported_state = ""
        self.log_count = 0
        self.histories = {k: deque([0.0] * 155, maxlen=155)
                          for k in ("ecg", "pleth", "resp", "cpr")}

        self.mode = tk.StringVar(value="default")
        self.source = tk.StringVar(value="virtual")
        self.scenario = tk.StringVar(value="Normal")
        self.port = tk.StringVar(value="COM3")
        self.speed = tk.DoubleVar(value=1.0)
        self.head = tk.DoubleVar(value=0.0)
        self.mock_tof = tk.DoubleVar(value=65.0)
        self.auto_breath = tk.BooleanVar(value=True)
        self.manual_head_fallback = tk.BooleanVar(value=False)
        self.tof_polarity = tk.StringVar(value="closer")
        self.sensor_head = None  # live head angle only when future IMU firmware emits it
        self.scanned = {"A2": set(), "B2": set()}
        self.good_scans = 0

        self._ui()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.note("Training-only simulation. Default mode ignores sensors.")
        self.after(80, self.tick)

    def label(self, parent, text, size=10, color=MUTED, bold=False):
        return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=color,
                        font=("Segoe UI", size, "bold" if bold else "normal"),
                        justify="left", anchor="w")

    def button(self, parent, text, action, color=CARD):
        return tk.Button(parent, text=text, command=action, bg=color, fg=INK,
                         activebackground="#224264", activeforeground=INK,
                         relief="flat", padx=10, pady=8, cursor="hand2",
                         font=("Segoe UI", 10, "bold"))

    def panel(self, parent):
        return tk.Frame(parent, bg=PANEL, highlightbackground="#24394c",
                        highlightthickness=1, padx=14, pady=12)

    def _ui(self):
        heading = tk.Frame(self, bg=BG, padx=20, pady=13)
        heading.pack(fill="x")
        tk.Label(heading, text="K.E.V.I.N.", bg=BG, fg=GREEN,
                 font=("Segoe UI", 25, "bold")).pack(side="left")
        tk.Label(heading, text="INFANT RESUSCITATION TRAINING  /  SYNTHETIC VITALS",
                 bg=BG, fg=MUTED, font=("Segoe UI", 10, "bold")).pack(side="left", padx=18)
        tk.Label(heading, text="NOT FOR PATIENT USE", bg="#50212d", fg="#ffb6c1",
                 padx=10, pady=5, font=("Segoe UI", 9, "bold")).pack(side="right")

        body = tk.Frame(self, bg=BG, padx=18)
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=5)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)
        monitor = self.panel(body)
        monitor.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        control_container = tk.Frame(body, bg=PANEL, highlightbackground="#24394c",
                                     highlightthickness=1)
        control_container.grid(row=0, column=1, sticky="nsew")
        scroll = tk.Canvas(control_container, bg=PANEL, highlightthickness=0)
        scroll.pack(side="left", fill="both", expand=True)
        scrollbar = tk.Scrollbar(control_container, command=scroll.yview)
        scrollbar.pack(side="right", fill="y")
        scroll.configure(yscrollcommand=scrollbar.set)
        controls = tk.Frame(scroll, bg=PANEL, padx=14, pady=12)
        inner = scroll.create_window((0, 0), window=controls, anchor="nw")
        controls.bind("<Configure>", lambda event: scroll.configure(scrollregion=scroll.bbox("all")))
        scroll.bind("<Configure>", lambda event: scroll.itemconfigure(inner, width=event.width))
        scroll.bind("<MouseWheel>", lambda event: scroll.yview_scroll(-int(event.delta / 120), "units"))
        controls.bind("<MouseWheel>", lambda event: scroll.yview_scroll(-int(event.delta / 120), "units"))

        self.state_label = self.label(monitor, "STABLE", size=12, color=GREEN, bold=True)
        self.state_label.pack(fill="x", pady=(0, 7))
        self.screen = tk.Canvas(monitor, bg="#060e17", highlightthickness=0,
                                height=490, bd=0)
        self.screen.pack(fill="both", expand=True)
        bottom = tk.Frame(monitor, bg=PANEL)
        bottom.pack(fill="x", pady=(9, 0))
        self.technical = self.label(bottom, "", size=9)
        self.technical.pack(anchor="w")
        self.explain = self.label(bottom, "", size=9, color=YELLOW)
        self.explain.pack(anchor="w", pady=(3, 0))

        self.label(controls, "RUN MODE", 10, INK, True).pack(fill="x", pady=(0, 4))
        for value, text in (("default", "DEFAULT  ·  autonomous monitor"),
                            ("reactive", "SENSOR-REACTIVE  ·  linked physiology")):
            tk.Radiobutton(controls, text=text, value=value, variable=self.mode,
                           command=self.changed_mode, bg=PANEL, fg=INK,
                           activebackground=PANEL, activeforeground=INK,
                           selectcolor="#214568", font=("Segoe UI", 9)).pack(anchor="w")
        self.label(controls, "SCENARIO OVERRIDE", 9, MUTED, True).pack(fill="x", pady=(13, 4))
        scenario_box = ttk.Combobox(controls, state="readonly", textvariable=self.scenario,
                                    values=("Normal", "Apnoea", "Choking", "Cardiac arrest"))
        scenario_box.pack(fill="x")
        scenario_box.bind("<<ComboboxSelected>>", self.scenario_changed)

        self.label(controls, "INPUT SOURCE (reactive mode)", 9, MUTED, True).pack(fill="x", pady=(14, 3))
        for value, text in (("virtual", "Virtual / interactive"), ("serial", "Real SensorHub COM3")):
            tk.Radiobutton(controls, text=text, value=value, variable=self.source,
                           command=self.changed_source, bg=PANEL, fg=INK,
                           activebackground=PANEL, activeforeground=INK,
                           selectcolor="#214568", font=("Segoe UI", 9)).pack(anchor="w")
        portrow = tk.Frame(controls, bg=PANEL)
        portrow.pack(fill="x", pady=(4, 0))
        tk.Entry(portrow, textvariable=self.port, width=7, font=("Consolas", 10),
                 bg=CARD, fg=INK, insertbackground=INK, relief="flat").pack(side="left", fill="x", expand=True)
        self.connection_button = self.button(portrow, "Connect COM", self.toggle_connection)
        self.connection_button.pack(side="right", padx=(6, 0))
        serial_commands = tk.Frame(controls, bg=PANEL)
        serial_commands.pack(fill="x", pady=(5, 0))
        for title, command in (("Select c", "c"), ("Scan i", "i"),
                               ("Status s", "s"), ("Acquire g", "g")):
            self.button(serial_commands, title, lambda c=command: self.serial_command(c)).pack(
                side="left", expand=True, fill="x", padx=2)
        imu_commands = tk.Frame(controls, bg=PANEL)
        imu_commands.pack(fill="x", pady=(5, 0))
        for title, command in (("Start IMU m", "m"), ("Zero tilt z", "z"),
                               ("Flip tilt f", "f"), ("Axis j", "j")):
            self.button(imu_commands, title, lambda c=command: self.serial_command(c)).pack(
                side="left", expand=True, fill="x", padx=2)
        self.label(controls, "Real head tilt: enable IMU m before acquire g.\nZero the IMU with head neutral; test physical flexion direction.", 8).pack(fill="x")
        self.sensor_health = self.label(controls, "LIVE: disconnected", size=9, color=YELLOW)
        self.sensor_health.pack(fill="x", pady=(7, 0))
        tk.Checkbutton(controls, text="Allow manual head fallback if IMU absent",
                       variable=self.manual_head_fallback, bg=PANEL, fg=INK,
                       activebackground=PANEL, activeforeground=INK,
                       selectcolor="#214568").pack(anchor="w", pady=(3, 2))
        self.label(controls, "Fallback is OFF by default: no real head data means no assumed neutral airway.", 8).pack(fill="x")

        tk.Frame(controls, height=1, bg="#30435a").pack(fill="x", pady=13)
        self.label(controls, "HEAD IMU (A1) • CHEST ASSUMED LEVEL", 9, INK, True).pack(fill="x")
        self.head_display = self.label(controls, "Head relative pitch: 0°", 10, BLUE)
        self.head_display.pack(fill="x", pady=(3, 0))
        self.scale(controls, self.head, -60, 60, 1)
        self.label(controls, "Manual pitch until IMU firmware publishes angles;\nnegative = flexion (toy convention).", 8).pack(fill="x")

        tk.Frame(controls, height=1, bg="#30435a").pack(fill="x", pady=10)
        self.label(controls, "PRESSURE / VENTILATION (A2)", 9, INK, True).pack(fill="x")
        tk.Checkbutton(controls, text="Auto virtual pressure breaths", variable=self.auto_breath,
                       bg=PANEL, fg=INK, activebackground=PANEL, activeforeground=INK,
                       selectcolor="#214568").pack(anchor="w", pady=(4, 5))
        self.button(controls, "Deliver simulated pressure breath", self.manual_breath, BLUE).pack(fill="x")
        self.label(controls, "Pressure pulse detected ≠ confirmed airflow.\nNo pulse for 4.5s → demo apnoea (not clinical).", 8).pack(fill="x", pady=5)

        tk.Frame(controls, height=1, bg="#30435a").pack(fill="x", pady=10)
        self.label(controls, "TOF / CPR DISPLACEMENT (B1)", 9, INK, True).pack(fill="x")
        self.tof_display = self.label(controls, "Virtual distance: 65 mm", 10, BLUE)
        self.tof_display.pack(fill="x")
        self.scale(controls, self.mock_tof, 10, 110, 1)
        self.button(controls, "Deliver simulated compression", self.manual_cpr, YELLOW).pack(fill="x")
        self.button(controls, "Calibrate ToF resting distance", self.calibrate_tof).pack(fill="x", pady=(5, 1))
        polar = tk.Frame(controls, bg=PANEL)
        polar.pack(fill="x", pady=4)
        for value, text in (("closer", "Closer"), ("farther", "Farther")):
            tk.Radiobutton(polar, text=text, value=value, variable=self.tof_polarity,
                           command=self.update_polarity, bg=PANEL, fg=MUTED,
                           activebackground=PANEL, activeforeground=INK,
                           selectcolor="#214568", font=("Segoe UI", 8)).pack(side="left")
        self.label(controls, "Relative movement only; not calibrated CPR depth.", 8).pack(fill="x")

        foot = tk.Frame(self, bg=BG, padx=18, pady=10)
        foot.pack(fill="x")
        self.button(foot, "RESET PATIENT", self.reset, RED).pack(side="left")
        self.label(foot, "Simulation speed", 9).pack(side="left", padx=(22, 8))
        ttk.Combobox(foot, width=7, textvariable=self.speed, state="readonly",
                     values=(1.0, 2.0, 4.0)).pack(side="left")
        self.label(foot, "EVENT LOG", 9, INK, True).pack(side="left", padx=(26, 10))
        self.events = tk.Text(foot, height=3, bg=PANEL, fg=MUTED, relief="flat",
                              font=("Consolas", 9), wrap="word", state="disabled")
        self.events.pack(side="left", fill="both", expand=True)

    def scale(self, parent, var, lo, hi, resolution):
        tk.Scale(parent, from_=lo, to=hi, orient="horizontal", variable=var,
                 resolution=resolution, bg=PANEL, fg=INK, activebackground=BLUE,
                 troughcolor="#233c55", highlightthickness=0, bd=0,
                 showvalue=False, length=180).pack(fill="x", pady=(1, 0))

    def note(self, text):
        if not hasattr(self, "events"):
            return
        self.events.config(state="normal")
        self.events.insert("end", f"[{self.model.time:05.1f}s] {text}\n")
        self.log_count += 1
        if self.log_count > 70:
            self.events.delete("1.0", "2.0")
        self.events.see("end")
        self.events.config(state="disabled")

    def changed_mode(self):
        self.reset()
        self.note(f"Mode changed: {self.mode.get().upper()}")

    def changed_source(self):
        self.reset()
        self.note(f"Input source: {self.source.get()}")

    def scenario_changed(self, _event=None):
        self.reset()
        self.note(f"Scenario: {self.scenario.get()} (instructor override)")

    def update_polarity(self):
        self.tof.polarity = self.tof_polarity.get()
        self.tof.reset()
        self.note(f"ToF direction: {self.tof_polarity.get()}; recalibrate at rest")

    def serial_command(self, command: str):
        if self.mode.get() != "reactive" or self.source.get() != "serial":
            self.note("Choose SENSOR-REACTIVE / Real SensorHub first")
            return
        if command in ("g", "m"):
            if self.good_scans < 2:
                self.note("Acquire blocked: need two clean scans with A1+A2+B1 present")
                return
            if not messagebox.askyesno(
                "Verify the hardware before starting",
                "Confirm A1=BHI360 IMU, A2=pressure ADC, B1=VL6180X ToF.\n\n"
                "The 'm' command uploads Bosch firmware to the BHI360 and "
                "requires the separately built EXPERIMENTAL live SensorHub image. "
                "The 'g' command reads/writes pressure and ToF registers.\n\n"
                "Do not proceed if connections are unverified or the scan "
                "shows abnormal addresses. Is this setup verified?"):
                return
        if command == "i":
            # The new scan will be counted only on its complete B-bus SCAN_END.
            pass
        if command in ("m", "z", "f", "j") and self.good_scans < 2:
            self.note("IMU control blocked: need two clean scans")
            return
        if self.serial.send(command):
            self.note(f"Sent v1 command: {command}")
        else:
            self.note("COM3 not connected (or command failed)")

    def toggle_connection(self):
        if self.serial.connected or (self.serial._thread and self.serial._thread.is_alive()):
            self.serial.stop()
            self.note("COM port disconnect requested")
        else:
            self.serial.start(self.port.get().strip() or "COM3")
            self.note("Opening COM port; close PlatformIO monitor first")

    def manual_breath(self):
        if self.mode.get() == "reactive" and self.source.get() == "virtual":
            self.model.breath()
            self.note("Virtual A2 pressure pulse")
        else:
            self.note("Breath button active only in reactive/virtual mode")

    def manual_cpr(self):
        if self.mode.get() == "reactive" and self.source.get() == "virtual":
            self.model.compression()
            self.note("Virtual B1 ToF compression pulse")
        else:
            self.note("CPR button active only in reactive/virtual mode")

    def calibrate_tof(self):
        self.tof.calibrate()
        self.note("ToF baseline set from last valid sample (if available)")

    def reset(self):
        self.model.reset()
        self.pressure.reset()
        self.tof.reset()
        self.last_pressure_wall = -1e6
        self.last_tof_wall = -1e6
        self.last_imu_wall = -1e6
        self.next_mock_breath = 0.0
        self.mock_tof_last = None
        self.sensor_head = None
        self.scanned = {"A2": set(), "B2": set()}
        self.good_scans = 0
        self.last_reported_state = ""
        for history in self.histories.values():
            history.clear()
            history.extend([0.0] * 155)
        self.note("Patient and sensor baselines reset")

    def _serial_events(self):
        while not self.serial.events.empty():
            try:
                reading = self.serial.events.get_nowait()
            except Exception:
                break
            if reading.kind == "connection":
                self.note(str(reading.value))
            elif reading.kind == "pressure":
                self.last_pressure_wall = time.monotonic()
                if self.pressure.feed(int(reading.value)):
                    self.model.breath()
                    self.note("Real pressure pulse: A2")
            elif reading.kind == "tof":
                self.last_tof_wall = time.monotonic()
                if self.tof.feed(float(reading.value), self.model.time):
                    self.model.compression()
                    self.note("Real ToF displacement: B1")
            elif reading.kind == "head_pitch":
                self.last_imu_wall = time.monotonic()
                self.sensor_head = float(reading.value)
            elif reading.kind == "imu_status":
                self.note(str(reading.value))
            elif reading.kind == "scan_start":
                bus = str(reading.value)
                self.scanned[bus] = set()
            elif reading.kind == "scan_found":
                bus, address = str(reading.value).split(":", 1)
                self.scanned[bus].add(int(address, 16))
            elif reading.kind == "scan_end":
                bus = str(reading.value)
                if bus == "B2":
                    expected = (self.scanned["A2"] == {0x15, 0x29, 0x68}
                                and self.scanned["B2"] == {0x29})
                    self.good_scans = self.good_scans + 1 if expected else 0
                    self.note(f"I2C scan: A={sorted(self.scanned['A2'])}, "
                              f"B={sorted(self.scanned['B2'])}; "
                              f"clean in a row={self.good_scans}")
            elif reading.kind == "pressure_fault":
                self.note(str(reading.value))

    def _settings(self, now):
        settings = Settings(mode=self.mode.get(), source=self.source.get(),
                            scenario=self.scenario.get(),
                            speed=1.0 if self.source.get() == "serial" else float(self.speed.get()))
        if self.mode.get() == "reactive":
            if self.source.get() == "virtual":
                settings.pressure_valid = True
                settings.head_pitch_deg = float(self.head.get())
            else:
                settings.pressure_valid = (self.serial.connected and
                                           now - self.last_pressure_wall < 2.2 and
                                           self.pressure.ready)
                settings.tof_valid = self.serial.connected and now - self.last_tof_wall < 2.2
                has_live_head = (self.serial.connected and self.sensor_head is not None
                                 and now - self.last_imu_wall < 2.2)
                settings.head_valid = has_live_head or self.manual_head_fallback.get()
                settings.head_pitch_deg = (float(self.sensor_head) if has_live_head
                                           else float(self.head.get()))
        return settings

    def tick(self):
        now = time.monotonic()
        dt = min(max(now - self.last_wall, 0), 0.2)
        self.last_wall = now
        self._serial_events()
        settings = self._settings(now)
        if (settings.mode == "reactive" and settings.source == "virtual"):
            if self.auto_breath.get() and self.model.time >= self.next_mock_breath:
                self.model.breath()
                self.next_mock_breath = self.model.time + 60 / 36
            mock = float(self.mock_tof.get())
            if self.tof.feed(mock, self.model.time):
                self.model.compression()  # one event per press/release cycle
            self.mock_tof_last = mock
        old_state = self.model.status
        self.model.step(dt, settings)
        if old_state != self.model.status and self.model.status != self.last_reported_state:
            self.note(self.model.status)
            self.last_reported_state = self.model.status
        for name, samples in self.histories.items():
            samples.append(self.model.sample_wave(name))
        self.render(settings)
        self.after(75, self.tick)

    def render(self, settings):
        data = self.model.display()
        self.state_label.config(text=data["status"],
                                fg=RED if "ARREST" in data["status"] else
                                YELLOW if data["status"] != "STABLE" else GREEN)
        self.head_display.config(text=f"Head relative pitch: {settings.head_pitch_deg:+.0f}°")
        if settings.source == "serial" and self.serial.connected:
            tof_text = (f"Real ToF distance: {self.tof.latest_mm:.0f} mm"
                        if settings.tof_valid and self.tof.latest_mm is not None
                        else "Real ToF: NO FRESH DATA")
        else:
            tof_text = f"Virtual ToF distance: {float(self.mock_tof.get()):.0f} mm"
        self.tof_display.config(text=tof_text)
        if settings.source == "serial":
            fresh_imu = (self.serial.connected and self.sensor_head is not None
                         and time.monotonic() - self.last_imu_wall < 2.2)
            head_state = "LIVE" if fresh_imu else ("MANUAL FALLBACK" if self.manual_head_fallback.get() else "NO DATA")
            pr = (str(self.pressure.latest) if settings.pressure_valid else "NO DATA")
            tof = (str(self.tof.latest_mm) if settings.tof_valid else "NO DATA")
            self.sensor_health.config(text=f"A1 head: {head_state}\nA2 pressure ADC: {pr}\nB1 ToF mm: {tof}")
        else:
            self.sensor_health.config(text="Virtual input (not measuring hardware)")
        connection = ("CONNECTED" if self.serial.connected else "NOT CONNECTED")
        self.connection_button.config(text="Disconnect" if self.serial.connected else "Connect COM")
        if settings.mode == "default":
            self.technical.config(text="DEFAULT • physiological scenario runs independently of all sensors")
        else:
            note = ("virtual input" if settings.source == "virtual" else
                    f"COM3 {connection} | pressure {'VALID' if settings.pressure_valid else 'NO DATA'}")
            self.technical.config(text=f"REACTIVE • {note} | Head chest-reference = 0° (assumed)")
        self.explain.config(text=f"Airway effectiveness: {self.model.airway * 100:.0f}% [toy model]  •  "
                                 f"ToF CPR activity: {data['cpr_rate']}/min  •  "
                                 "SpO₂/HR/EtCO₂ are SIMULATED, not measured")
        canvas = self.screen
        w = max(canvas.winfo_width(), 720)
        h = max(canvas.winfo_height(), 450)
        canvas.delete("all")
        plot_width = w * 0.71
        canvas.create_line(plot_width, 0, plot_width, h, fill="#24364b", width=2)
        rows = (("ecg", GREEN, "ECG • synthetic", 0.13, 43),
                ("pleth", BLUE, "PLETH • synthetic", 0.36, 43),
                ("resp", YELLOW, "RESP • sensor pressure pulses", 0.59, 43),
                ("cpr", RED, "CPR • ToF detected movements", 0.82, 43))
        for name, color, title, fraction, amplitude in rows:
            baseline = h * fraction + 35
            canvas.create_text(14, baseline - 68, text=title, anchor="nw", fill=MUTED,
                               font=("Segoe UI", 10, "bold"))
            for x in range(0, int(plot_width), 45):
                canvas.create_line(x, baseline - 58, x, baseline + 18, fill="#12283a")
            canvas.create_line(0, baseline, plot_width - 12, baseline, fill="#244154")
            values = list(self.histories[name])
            coords = []
            for idx, val in enumerate(values):
                x = 7 + idx * (plot_width - 24) / max(1, len(values) - 1)
                y = baseline - val * amplitude
                coords.extend([x, y])
            if len(coords) > 3:
                canvas.create_line(coords, fill=color, width=2.25, smooth=True)
        digits = (("HR", f"{data['hr']}", "BPM", GREEN),
                  ("SpO₂", "--" if data['spo2'] is None else f"{data['spo2']}", "%", BLUE),
                  ("RESP", f"{data['rr']}", "/MIN", YELLOW),
                  ("EtCO₂", "--" if data['etco2'] is None else f"{data['etco2']}", "mmHg*", YELLOW),
                  ("BP", data["bp"], "mmHg*", INK))
        gap = h / (len(digits) + 0.25)
        for i, (name, val, unit, color) in enumerate(digits):
            x = plot_width + 20
            y = 15 + i * gap
            canvas.create_text(x, y, text=name, fill=MUTED, anchor="nw",
                               font=("Segoe UI", 10, "bold"))
            canvas.create_text(x, y + 21, text=val, fill=color, anchor="nw",
                               font=("Consolas", 28 if len(val) < 4 else 23, "bold"))
            canvas.create_text(x + 128, y + 37, text=unit, fill=MUTED, anchor="nw",
                               font=("Segoe UI", 9))
        canvas.create_text(w - 12, h - 7, text="* illustrative • not a measurement",
                           fill="#647e97", anchor="se", font=("Segoe UI", 8))

    def close(self):
        self.serial.stop()
        self.destroy()


if __name__ == "__main__":
    MonitorApp().mainloop()
