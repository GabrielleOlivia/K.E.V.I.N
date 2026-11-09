from pathlib import Path
import matplotlib.pyplot as plt

PROJECT_ROOT = Path(__file__).resolve().parent.parent

LOG_FILE = PROJECT_ROOT / "data" / "pressure_20260922_145124.txt"


time_ms = []
raw_values = []
baselines = []
deltas = []
states = []
candidate_counts = []


with LOG_FILE.open("r", encoding="utf-8", errors="ignore") as file:
    for line in file:
        line = line.strip()

        # Ignore empty lines, comments and miniterm messages
        if not line:
            continue

        if line.startswith("#"):
            continue

        if line.startswith("---"):
            continue

        parts = line.split(",")

        # Normal data rows contain 8 columns
        if len(parts) != 8:
            continue

        try:
            timestamp = int(parts[0])
            raw = int(parts[1])

            # Calibration rows don't have a baseline/delta yet
            if parts[2] == "" or parts[3] == "":
                continue

            baseline = int(parts[2])
            delta = int(parts[3])

            state = parts[4]
            candidate_count = int(parts[5])

        except ValueError:
            continue

        time_ms.append(timestamp)
        raw_values.append(raw)
        baselines.append(baseline)
        deltas.append(delta)
        states.append(state)
        candidate_counts.append(candidate_count)


if not time_ms:
    raise RuntimeError("No usable pressure data was found.")


# --------------------------------------------------
# Convert timestamp to seconds from start
# --------------------------------------------------

start_time = time_ms[0]

time_seconds = [
    (timestamp - start_time) / 1000.0
    for timestamp in time_ms
]


# --------------------------------------------------
# Print basic information
# --------------------------------------------------

print()
print("Pressure log loaded successfully")
print("--------------------------------")
print(f"File: {LOG_FILE}")
print(f"Samples: {len(raw_values)}")
print(f"Starting candidate count: {candidate_counts[0]}")
print(f"Ending candidate count:   {candidate_counts[-1]}")
print(f"Minimum delta: {min(deltas)}")
print(f"Maximum delta: {max(deltas)}")
print()


# --------------------------------------------------
# Plot
# --------------------------------------------------

plt.figure(figsize=(14, 6))

plt.plot(
    time_seconds,
    deltas,
    label="Pressure relative to baseline"
)

# Event thresholds used by current firmware
plt.axhline(
    y=200,
    linestyle="--",
    label="Positive threshold (+200)"
)

plt.axhline(
    y=-200,
    linestyle="--",
    label="Negative threshold (-200)"
)

# Zero = baseline
plt.axhline(
    y=0,
    linewidth=1
)

plt.xlabel("Time (seconds)")
plt.ylabel("Raw ADC difference from baseline")

plt.title(
    "K.E.V.I.N Respiratory Pressure PoC — Three-Push Test"
)

plt.grid(True)
plt.legend()

plt.tight_layout()

OUTPUT_FILE = (
    PROJECT_ROOT
    / "plots"
    / "pressure_20260922_145124_three_push.png"
)

OUTPUT_FILE.parent.mkdir(
    parents=True,
    exist_ok=True
)

plt.savefig(
    OUTPUT_FILE,
    dpi=200,
    bbox_inches="tight"
)

print(f"Plot saved to: {OUTPUT_FILE}")

plt.show()