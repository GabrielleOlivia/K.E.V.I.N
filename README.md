# Pressure Sensor Test for the ModularSim SensorHub

Phase 1 respiratory pressure-sensing proof of concept for the Advanced Life Support Monitor Simulator infant-manikin project.

This README describes the latest working candidate-ventilation firmware recorded in the worklog dated 21 September 2026. Use that version of `src/main.cpp`; the original recovery ZIP contained an incorrect Sensor A2 pin mapping.

## Current status

Bench testing has demonstrated communication with the pressure module, acquisition of raw ADC samples, and detection of positive and negative pressure excursions caused by a hand-operated syringe.

The firmware:

- Measures a resting baseline at startup.
- Detects positive and negative pressure events separately.
- Records peak or minimum deviation and event duration.
- Counts completed positive events as `CANDIDATE VENTILATION` events.
- Measures the interval between the starts of successive positive events.
- Prints results over USB serial.

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
| `notes/known_good_usb_serial_test.cpp` | Optional separate USB serial fallback, if retained from the recovery project |

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
9. After calibration succeeds, apply a gentle pressure change and observe the event output.

If calibration fails, stop the test and investigate. The current firmware prints an error but does not yet automatically disable detection after calibration failure.

## Expected output

An illustrative excerpt from the recorded candidate-event run is:

```text
Baseline = 2533
Detector ready.

>>> POSITIVE PRESSURE START
>>> POSITIVE PRESSURE END

CANDIDATE VENTILATION #1
Peak RAW change = +574
Event duration = 3614 ms
First candidate event - no previous interval.
```

Negative excursions are reported separately and do not increment the positive-event counter. Later positive events also report the interval since the previous candidate event started.

The latest firmware prints event summaries. It does not print the old I2C scan banner or continuously stream every raw sample. Baseline and event values above are examples from a bench run, not required values or clinical targets.

## Bench success criteria

- Startup obtains ADC samples and establishes a resting baseline.
- Deliberate syringe pressure changes produce clear deviations from that baseline.
- A sustained positive excursion followed by recovery produces one completed candidate event in the demonstrated test conditions.
- A negative excursion is reported separately.
- The signal returns close to its resting level after pressure is released.

Resting readings in the recorded experiments were approximately 2515 to 2550 counts. A similar baseline alone does not establish correct pressure calibration.

## Current limitations and next work

- Start and return thresholds are provisional: 200 and 80 raw counts. Reassess them for the actual pneumatic setup.
- The current 100 ms conversion delay and 50 ms loop delay limit acquisition to roughly 6.7 samples per second before other overhead.
- Add timestamped raw-sample logging for waveform analysis.
- Add calibration-validity checks and handling for interrupted readings and unfinished events.
- Verify the physical board's sensor supply and analog scaling.
- Test controlled, repeatable inputs through tubing and a compliant test lung, then introduce leaks and restrictions.
- When the manikin is available, test whether CPR produces false candidate-ventilation events.
- Pressure alone does not establish delivered volume or ventilation effectiveness. Use independent evidence of lung filling and evaluate flow sensing before promoting candidates to validated ventilation events.

The proposed faster acquisition, additional logging and fault handling are future work; this README does not imply that they have already been implemented.

## Troubleshooting

If readings fail, record the serial output and check the USB serial port, Sensor A2 connection, power and verified PA16/PA17/SERCOM1 configuration. An I2C presence test can check whether `0x68` responds. Keep diagnostic firmware separate from the saved working detector.

Build/upload success verifies programming, not communication with the pressure module. Do not return to the superseded PA12/PA13 mapping when troubleshooting Sensor A2.
