# Pressure Sensor Test for the ModularSim SensorHub

Phase 1 respiratory pressure-sensing proof of concept for the Advanced Life Support Monitor Simulator infant-manikin project.

This version adds sample logging and calibration checks to the candidate-ventilation firmware recorded in the worklog dated 21 September 2026. The update passes 12 host tests using simulated ADC and serial inputs. A PlatformIO build for the SAMD21 and a physical bench test are still required. Follow [the logging bench test](notes/pressure_logging_bench_test.md) before collecting experimental data.

## Current status

Bench testing has demonstrated communication with the pressure module, acquisition of raw ADC samples, and detection of positive and negative pressure excursions caused by a hand-operated syringe.

The firmware:

- Requires 30 successful startup samples with a maximum spread of 80 raw counts before accepting a baseline.
- Keeps the accepted baseline fixed during a measurement run; send `z` over USB serial to recalibrate at rest.
- Detects positive and negative pressure events separately.
- Records peak or minimum deviation and event duration.
- Counts completed positive events as `CANDIDATE VENTILATION` events.
- Measures the interval between the starts of successive positive events.
- Prints a timestamped CSV row for every read attempt, including sample and baseline validity flags.
- Disables counting and discards unfinished events after a failed reading or failed calibration.
- Preserves completed event counts across recalibration; a board reset clears the count.

These are candidate events, not validated infant breaths. The firmware does not yet measure calibrated pressure in kPa, measure airflow or delivered volume, assess ventilation effectiveness, or update `PatientState`. Intervals from random syringe movements are not physiological respiratory-rate measurements.

## Hardware and verified configuration

| Item | Configuration verified in the bench setup |
|---|---|
| SensorHub | ModularSim v1.2.2, SAMD21, Micro-USB programming and serial |
| Pressure module | SimModule Pressure v2.0.0, January 2026 |
| Pressure sensor fitted | MPXV5010GP |
| ADC | MCP3426, channel 1 |
| ADC I2C address | `0x68` |
| SensorHub connector | Sensor A2 |
| SDA MCU pad | PA16 |
| SCL MCU pad | PA17 |
| SDA Arduino index | `11`, under the Feather M0 Express variant |
| SCL Arduino index | `13`, under the Feather M0 Express variant |
| I2C peripheral | SERCOM1 |
| Pin mux | `PIO_SERCOM` |
| I2C clock | 100 kHz |
| ADC configuration | `0x88`: channel 1, one-shot, 16-bit, gain x1 |
| Serial monitor | 115200 baud |

The custom `TwoWire` instance uses SERCOM1 and a matching `SERCOM1_Handler()` that calls `WireSensorA.onService()`.

PA12/PA13 and SERCOM2 were used in superseded attempts and are not the verified Sensor A2 route. Arduino pin indices depend on the selected board variant; distinguish them from physical MCU pad names.

## Documentation mismatch

The older schematic `Pressure_Module_v2.1_jan2024` names an MP3V5050 sensor and labels its four-wire interface GND, 3.3 V, SCL and SDA. The physical pressure module contains an MPXV5010GP. The older drawing is useful background but does not establish the exact supply, connector pin order or analog scaling of the current board.

Use the existing verified cable and keyed Sensor A2 connection. Verify the current board revision before making a replacement cable or changing supplies. Power the SensorHub off before connecting or disconnecting the module.

Continue reporting raw counts or clearly labelled ADC input-equivalent voltage until the current sensor supply and analog signal path are verified and pressure calibration is performed against a reference.

## Project files

Open the project folder that contains `platformio.ini`.

| Path | Purpose |
|---|---|
| `platformio.ini` | PlatformIO build, upload and serial configuration |
| `src/main.cpp` | Latest working candidate-ventilation detector |
| `README.md` | Setup, verified configuration and limitations |
| `notes/pressure_logging_bench_test.md` | Build, sample logging and calibration-failure bench checks |
| `notes/known_good_usb_serial_test.cpp` | Optional separate USB serial fallback, if retained from the recovery project |
| `tests/` | Host tests and Arduino/I2C substitutes; not part of the board firmware |

Keep the fallback outside `src/` so it is not compiled alongside the main firmware.

## PlatformIO configuration

```ini
[env:adafruit_feather_m0_express]
platform = atmelsam
board = adafruit_feather_m0_express
framework = arduino
monitor_speed = 115200

; Only set these if automatic port detection fails.
; Change COM3 to the actual USB serial port on your computer.
; upload_port = COM3
; monitor_port = COM3
```

The Feather M0 Express definition is the build/upload target used successfully for this custom SAMD21 board; it does not mean the physical SensorHub is a Feather board.

## Open, build and run

1. Open VS Code with the PlatformIO IDE extension enabled.
2. Choose **File > Open Folder** and select the folder containing `platformio.ini`.
3. With the SensorHub powered off, connect the pressure module to Sensor A2 using the verified cable.
4. Connect the SensorHub to the laptop using a Micro-USB data cable.
5. Stop Serial Monitor if it is running. Select **Build**, then **Upload** in PlatformIO.
6. Open PlatformIO Serial Monitor at 115200 baud on the SensorHub's USB serial port. COM3 was used in the recorded test; the port can change.
7. Keep the pressure port at rest and do not move the syringe during baseline calibration.
8. If you missed startup, reset the board and reconnect Serial Monitor if needed. USB serial may briefly disappear during reset.
9. Wait for `# READY`. After calibration succeeds, apply a gentle pressure change and observe the CSV rows and event comments.

If calibration fails, counting remains disabled. Successful reads can still appear, but their state is `CAL_REQUIRED` and `baseline_ok` is `0`. Resolve the cause, leave the pressure at rest, then type `z` in Serial Monitor to retry calibration. If changing module connections, power off first and reset the setup afterward. The software stability check cannot detect a steady pressure incorrectly applied during zeroing; calibration must be performed with the pressure at rest.

## Expected output

An illustrative excerpt of the new format is shown below. These rows describe the format; they are not new hardware measurements.

```text
t_ms,raw,baseline,delta,state,candidate_count,sample_ok,baseline_ok
# READY: baseline_raw=2540; counting enabled. Send z to recalibrate.
5100,2542,2540,2,IDLE,0,1,1
# POSITIVE_PRESSURE_START
5250,3000,2540,460,POSITIVE_EVENT,0,1,1
# CANDIDATE_VENTILATION count=1, peak_delta_raw=460, duration_ms=150
5400,2540,2540,0,IDLE,1,1,1
```

Negative excursions are reported separately and do not increment the positive-event counter. Later positive events report the interval since the previous candidate event started, provided no fault or recalibration interrupted that sequence. All diagnostic and event messages start with `#`, so a CSV reader can skip them.

`t_ms` is the read-completion time in milliseconds since boot. `raw`, `baseline` and `delta` are ADC counts. `sample_ok` indicates a successful ADC response; `baseline_ok` indicates software acceptance of the baseline. Missing values are empty fields, not zero. The logged state and count reflect event processing for that row. The header prints once at startup; capture it when saving a new log. The firmware retains the proven one-shot 16-bit acquisition configuration, with about 6.7 samples per second before other overhead.

## Bench success criteria

- Startup accepts a resting baseline only after all 30 reads succeed and the sample spread is no more than 80 counts.
- Deliberate syringe pressure changes produce clear deviations from that baseline.
- A sustained positive excursion followed by recovery produces one completed candidate event in the demonstrated test conditions.
- A negative excursion is reported separately.
- The signal returns close to its resting level after pressure is released.
- A failed read cancels an unfinished event and prevents further counting until calibration succeeds again.
- Baseline drift remains visible against the fixed calibration value; recalibrate at rest between runs if necessary.

Resting readings in the recorded experiments were approximately 2515 to 2550 counts. A similar baseline alone does not establish correct pressure calibration.

## Current limitations and next work

- Start and return thresholds are provisional: 200 and 80 raw counts. Reassess them for the actual pneumatic setup.
- The current 100 ms conversion delay and 50 ms loop delay limit acquisition to roughly 6.7 samples per second before other overhead.
- Timestamped logging and calibration/fault checks are implemented in this update; confirm their operation on the SensorHub using the bench test.
- Evaluate faster acquisition separately, updating count/voltage scaling if the ADC resolution changes.
- Verify the physical board's sensor supply and analog scaling.
- Test controlled, repeatable inputs through tubing and a compliant test lung, then introduce leaks and restrictions.
- When the manikin is available, test whether CPR produces false candidate-ventilation events.
- Pressure alone does not establish delivered volume or ventilation effectiveness. Use independent evidence of lung filling and evaluate flow sensing before promoting candidates to validated ventilation events.

Faster acquisition, physical pressure calibration, and validation of ventilation effectiveness remain future work. Software acceptance of a stable baseline does not verify the sensor's supply, calibration or pneumatic connection.

## Run the host checks

On a computer with a C++11 compiler, run from the repository root:

```sh
g++ -std=c++11 -Wall -Wextra -Werror -I tests/stubs tests/pressure_logger_host_test.cpp -o /tmp/kevin-pressure-logger-test
/tmp/kevin-pressure-logger-test
```

These checks exercise the firmware against simulated readings, including calibration failure, positive and negative events, interrupted events, malformed ADC responses, manual recalibration and CSV formatting. They do not exercise the SAMD21 toolchain, real I2C timing or USB serial.

## Troubleshooting

If readings fail, record the serial output and check the USB serial port, Sensor A2 connection, power and verified PA16/PA17/SERCOM1 configuration. An I2C presence test can check whether `0x68` responds. Keep diagnostic firmware separate from the saved working detector.

Build/upload success verifies programming, not communication with the pressure module. Do not return to the superseded PA12/PA13 mapping when troubleshooting Sensor A2.
