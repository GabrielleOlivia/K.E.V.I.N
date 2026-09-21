PRESSURE SENSOR TEST — MODULARSIM SENSORHUB
===========================================

WHAT THIS PROJECT IS
--------------------
This is the small Phase-1 proof-of-concept project we were building.

It tests this path:

Air pressure
  -> MPXV5010GP pressure sensor
  -> analog voltage
  -> MCP3426 ADC
  -> I2C
  -> SensorHub SAMD21
  -> USB Serial
  -> laptop

It does NOT yet:
- convert the reading to kPa,
- detect breaths,
- classify ventilation,
- update PatientState.

We first want to prove that the SensorHub can see the MCP3426 and that
the ADC value changes when pressure changes.


HOW TO OPEN IT
--------------
1. Extract this ZIP somewhere on your computer.
2. Open VS Code.
3. File -> Open Folder...
4. Select the extracted "PressureSensorTest" folder.
5. Make sure PlatformIO IDE is enabled/trusted.


HARDWARE
--------
SensorHub:
- SAMD21
- programmed over Micro-USB

Pressure module:
- physical board contains MPXV5010GP
- MCP3426 ADC
- 4-pin connector

Pressure-module connector documented as:
P1 = GND
P2 = 3.3 V
P3 = SCL
P4 = SDA

For this test, use the Sensor A2 connector.

IMPORTANT:
Power the SensorHub OFF before plugging/unplugging the pressure module.
Do not force the keyed connector.


BUILD / UPLOAD
--------------
1. First leave the pressure module disconnected.
2. Connect SensorHub to laptop with Micro-USB.
3. In PlatformIO click Build (check mark).
4. Then Upload (right arrow).

If PlatformIO cannot find the USB port:
- run PlatformIO -> Devices,
- find the USB Serial Device,
- edit platformio.ini and uncomment:
    upload_port = COM3
    monitor_port = COM3
- change COM3 to your actual COM number.


PRESSURE TEST
-------------
After the firmware uploads successfully:

1. Stop Serial Monitor if it is running.
2. Unplug USB so the SensorHub is powered off.
3. Connect the Pressure SimModule to Sensor A2.
4. Plug USB back in.
5. Open PlatformIO Serial Monitor at 115200 baud.

Expected startup output should look similar to:

    Scanning Sensor A2 I2C bus...
      Found I2C device at 0x68
    MCP3426 found at address 0x68.
    Starting CH1 readings...

Then repeated lines should appear:

    RAW: 1234    Voltage: 0.077125 V
    RAW: 1236    Voltage: 0.077250 V
    ...

The numbers above are examples only.

FIRST SUCCESS CRITERION
-----------------------
MCP3426 is detected at 0x68 and repeated ADC readings appear.

SECOND SUCCESS CRITERION
------------------------
When pressure at the pressure-sensor port changes gently, the raw reading
changes clearly and returns toward baseline after release.

Do NOT invent a breath threshold yet. First collect real measurements.


NOTE ABOUT THE SENSORHUB I2C PINS
---------------------------------
This project uses:
- SDA = Arduino pin 28 = PA12
- SCL = Arduino pin 39 = PA13
- SERCOM2 using the normal SERCOM pin mux

This is a self-contained test and does not require the old
WireScanner.h or TwiPinHelper.h helper files.


IF 0x68 IS NOT FOUND
--------------------
Do not start changing random wiring.

Record exactly what the Serial Monitor says and check:
- pressure module is on Sensor A2,
- connector orientation/keying,
- SensorHub is powered,
- I2C scan result.

Then troubleshoot the bus configuration before doing anything with
pressure conversion or breath detection.
