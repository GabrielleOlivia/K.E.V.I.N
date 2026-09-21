PRESSURE SENSOR TEST — MODULARSIM SENSORHUB
===========================================

PROJECT
-------
K.E.V.I.N
Advanced Life Support Infant Monitor Simulator

This directory contains the current Phase-1 respiratory pressure
proof-of-concept.

The purpose of this PoC is to investigate whether the existing
Pressure SimModule and SensorHub can be used to detect pressure-related
events that may eventually contribute to ventilation detection in the
infant manikin.


CURRENT VERIFIED SIGNAL PATH
----------------------------

Air pressure
  -> MPXV5010GP pressure sensor
  -> analog voltage
  -> MCP3426 ADC
  -> I2C
  -> SensorHub SAMD21
  -> pressure sampling
  -> baseline estimation
  -> positive / negative pressure event detection
  -> candidate ventilation event counting
  -> USB Serial
  -> laptop


CURRENT STATUS
--------------
The following functionality has been successfully demonstrated:

- SensorHub firmware builds and uploads using PlatformIO.
- USB serial communication with the SAMD21 works.
- Pressure SimModule is connected through Sensor A2.
- MCP3426 responds at I2C address 0x68.
- MCP3426 channel 1 ADC readings are successfully acquired.
- Resting pressure produces a relatively stable raw baseline.
- Applying positive pressure with a syringe increases the raw ADC value.
- Pulling the syringe produces a raw value below the resting baseline.
- The signal returns toward baseline after pressure is released.
- Individual positive pressure events can be detected.
- Individual negative pressure events can be detected.
- Positive events can be counted as CANDIDATE VENTILATION events.
- Event peak magnitude can be recorded.
- Event duration can be measured.
- Time between candidate events can be measured.


IMPORTANT LIMITATION
--------------------
The current test uses a syringe operated manually and randomly.

Therefore:

- Candidate ventilation events are NOT yet validated breaths.
- Event intervals are NOT yet respiratory rate.
- Raw ADC magnitude is NOT yet a measure of ventilation quality.
- The pressure reading is NOT yet converted to calibrated pressure units.
- No clinical thresholds have been defined.
- No "normal", "reduced", or "obstructed" ventilation thresholds have
  been validated.

The current software proves pressure-event detection only.


HARDWARE
--------
SensorHub:
- ModularSim SensorHub v1.2.2
- SAMD21 / Cortex-M0+
- programmed over Micro-USB

Pressure module:
- Pressure SimModule
- physical board marked v2.0.0
- MPXV5010GP pressure sensor
- MCP3426 ADC
- 4-pin sensor connector

The available older pressure-module schematic documents the connector as:

P1 = GND
P2 = 3.3 V
P3 = SCL
P4 = SDA

NOTE:
The older schematic documents a different pressure-sensor part number
than the physical module currently being tested.

Therefore the old schematic must not be assumed to completely describe
the physical 2026 pressure module.

For the current PoC, the pressure module is connected to Sensor A2.


SENSOR A2 I2C CONFIGURATION
---------------------------
This is the verified working configuration.

Sensor A2:

SDA:
- Arduino pin 11
- SAMD21 PA16

SCL:
- Arduino pin 13
- SAMD21 PA17

Peripheral:
- SERCOM1
- normal SERCOM pin mux

Firmware configuration:

    #define SENSOR_A_SDA 11
    #define SENSOR_A_SCL 13

    TwoWire WireSensorA(
        &sercom1,
        SENSOR_A_SDA,
        SENSOR_A_SCL
    );

    void SERCOM1_Handler()
    {
        WireSensorA.onService();
    }

Initialization:

    WireSensorA.begin();

    pinPeripheral(SENSOR_A_SDA, PIO_SERCOM);
    pinPeripheral(SENSOR_A_SCL, PIO_SERCOM);

    WireSensorA.setClock(100000);


MCP3426
-------
Verified I2C address:

    0x68

Current ADC configuration:

    0x88

Current implementation uses:
- channel 1
- one-shot conversion
- 16-bit mode
- gain x1

The current voltage conversion used in firmware is:

    voltage = rawValue * (2.048 / 32768.0)


PLATFORMIO
----------
Current PlatformIO environment:

    [env:adafruit_feather_m0_express]
    platform = atmelsam
    board = adafruit_feather_m0_express
    framework = arduino
    monitor_speed = 115200

The SensorHub SAMD21 is currently programmed using the
Adafruit Feather M0 Express PlatformIO configuration.


BUILD / UPLOAD
--------------
Connect the SensorHub to the laptop using Micro-USB.

In VS Code with PlatformIO:

1. Build the project.
2. Upload the firmware.
3. Open Serial Monitor.
4. Use 115200 baud.

The SensorHub currently appears as COM3 on the development laptop,
but COM port numbering may change between computers or USB connections.


I2C VERIFICATION
----------------
The MCP3426 was successfully detected using:

    Trying MCP3426 at 0x68...
    I2C result = 0
    *** MCP3426 FOUND ***

This verified:

- Sensor A2 communication is functional.
- PA16 / PA17 configuration is functional.
- SERCOM1 is functional.
- the pressure module is powered sufficiently to communicate.
- the MCP3426 is responding on the bus.


RAW PRESSURE TEST
-----------------
Typical resting readings observed during development were approximately:

    RAW ~ 2530 to 2550

Example positive-pressure behaviour:

    resting ~2520
    pressure applied
    raw increases into the thousands
    pressure released
    raw returns toward baseline

Example negative-pressure behaviour:

    resting ~2530
    syringe pulled
    raw falls below baseline
    release
    raw returns toward baseline

Therefore the experimentally observed direction is:

    RAW > baseline
        positive applied pressure

    RAW approximately baseline
        resting condition

    RAW < baseline
        pressure below resting baseline / syringe suction


PRESSURE EVENT DETECTOR
-----------------------
The current firmware uses a simple state machine:

    IDLE
      |
      +--> POSITIVE_EVENT
      |
      +--> NEGATIVE_EVENT

Current experimental thresholds:

    EVENT_THRESHOLD = 200
    RETURN_THRESHOLD = 80

These values were selected for the current bench PoC because baseline
variation was much smaller than the syringe-generated pressure changes.

They are NOT physiological thresholds.


CANDIDATE VENTILATION
---------------------
Positive pressure events are currently counted as:

    CANDIDATE VENTILATION

This terminology is deliberate.

A positive syringe-pressure event demonstrates that the system can
detect and count an event that could potentially correspond to
positive-pressure ventilation later.

It has NOT yet been demonstrated that the same algorithm reliably
detects actual ventilation through the infant manikin airway.


CURRENT EXPERIMENTAL RESULTS
----------------------------
The event detector successfully detected multiple separate positive
and negative syringe events.

Example:

    >>> POSITIVE PRESSURE START
    >>> POSITIVE PRESSURE END

    CANDIDATE VENTILATION #1
    Peak RAW change = +574
    Event duration = 3614 ms

Negative events were recorded separately:

    >>> NEGATIVE PRESSURE START
    >>> NEGATIVE PRESSURE END

    Minimum RAW change = -798
    Event duration = 3915 ms

Additional testing successfully counted candidate ventilation events
sequentially while also recording their duration and the interval
between positive events.


IMPORTANT INTERPRETATION
------------------------
The syringe was operated manually.

Large differences were observed between positive-pressure peaks.

This does NOT show that the pressure detector is unreliable.

It shows that the physical syringe input was uncontrolled.

Therefore a fixed raw ADC value must NOT currently be interpreted as:

- a correct breath,
- an incorrect breath,
- sufficient ventilation,
- insufficient ventilation,
- a specific pressure,
- a specific tidal volume.


CURRENT SOFTWARE ARCHITECTURE
-----------------------------

Physical pressure
        |
        v
MPXV5010GP
        |
        v
Analog voltage
        |
        v
MCP3426 ADC
        |
        | I2C
        v
SensorHub SAMD21
        |
        v
Raw ADC samples
        |
        v
Baseline estimation
        |
        v
Pressure difference
        |
        v
Pressure event state machine
        |
        +--> POSITIVE PRESSURE EVENT
        |
        +--> NEGATIVE PRESSURE EVENT
        |
        v
Candidate ventilation counter / timing
        |
        v
USB Serial output


WHAT HAS NOT BEEN IMPLEMENTED YET
---------------------------------
The current PoC does NOT yet:

- convert raw ADC readings to validated airway pressure,
- measure airflow,
- measure tidal volume,
- detect clinically validated breaths,
- calculate a validated respiratory rate,
- distinguish effective from ineffective ventilation,
- detect airway obstruction reliably,
- detect mask leak,
- control chest-rise hardware,
- control pumps or valves,
- update the central PatientState,
- communicate respiratory events to the Raspberry Pi,
- simulate respiratory deterioration,
- drive the real patient monitor.


NEXT ENGINEERING STEP
---------------------
The next useful experiment is not simply adding more software.

The pressure sensing system should be connected to a more realistic
respiratory setup containing some combination of:

    air source / ventilation input
            |
            v
         airway
            |
            v
    pressure sensing point
            |
            v
    resistance / tubing
            |
            v
       compliant lung

The next experiments should investigate whether the pressure signal can
distinguish conditions such as:

- effective ventilation,
- reduced ventilation,
- restricted / obstructed airway,
- no ventilation.

These classifications must be based on controlled experiments rather
than arbitrary thresholds.


SAFETY / HANDLING
-----------------
Power the SensorHub off before changing module connections.

Do not force connectors.

Use gentle pressure during bench testing.

Do not assume the allowable positive or negative pressure range until
the exact physical pressure sensor configuration has been verified.

This project is for simulation and training use only.

It must not be connected to a human patient.


PHASE-1 RESULT
--------------
The current proof of concept demonstrates that the available pressure
module can be read successfully through the existing SensorHub and that
software running on the SAMD21 can identify discrete pressure events.

The verified path is:

Pressure
  -> MPXV5010GP
  -> MCP3426
  -> I2C
  -> SensorHub SAMD21
  -> pressure samples
  -> event detection
  -> candidate ventilation events

The next phase is to determine how these pressure events relate to
actual manikin ventilation.
