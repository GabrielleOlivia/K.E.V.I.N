#include <Arduino.h>
#include <Wire.h>
#include "wiring_private.h"

// Sensor A2: Feather M0 Express variant indices for PA16 and PA17.
#define SENSOR_A_SDA 11
#define SENSOR_A_SCL 13
#define MCP3426_ADDR 0x68

TwoWire WireSensorA(&sercom1, SENSOR_A_SDA, SENSOR_A_SCL);

void SERCOM1_Handler()
{
    WireSensorA.onService();
}

// Provisional raw-count thresholds for this bench setup, not clinical limits.
const int EVENT_THRESHOLD = 200;
const int RETURN_THRESHOLD = 80;
const int CALIBRATION_SAMPLES = 30;
const int MAX_CALIBRATION_SPREAD = 80;

enum PressureState
{
    IDLE,
    POSITIVE_EVENT,
    NEGATIVE_EVENT
};

PressureState pressureState = IDLE;
bool baselineValid = false;
int32_t baseline = 0;
int16_t peakValue = 0;
int16_t minimumValue = 0;
unsigned long eventStartTime = 0;
unsigned long candidateCount = 0;
unsigned long previousCandidateTime = 0;
bool havePreviousCandidate = false;

// Keep the proven CH1, one-shot, 16-bit, gain-x1 acquisition configuration.
bool readPressureADC(int16_t &rawValue)
{
    const uint8_t config = 0x88;
    WireSensorA.beginTransmission(MCP3426_ADDR);
    WireSensorA.write(config);
    if (WireSensorA.endTransmission() != 0)
    {
        return false;
    }

    delay(100);
    const uint8_t count = WireSensorA.requestFrom(MCP3426_ADDR, (uint8_t)3);
    if (count != 3)
    {
        // Discard a partial response; never use it as a pressure sample.
        while (WireSensorA.available())
        {
            WireSensorA.read();
        }
        return false;
    }

    const uint8_t highByte = WireSensorA.read();
    const uint8_t lowByte = WireSensorA.read();
    const uint8_t status = WireSensorA.read();
    // RDY must be clear and the returned configuration must match our request.
    if ((status & 0x80) || ((status & 0x7F) != (config & 0x7F)))
    {
        return false;
    }

    rawValue = (int16_t)(((uint16_t)highByte << 8) | lowByte);
    return true;
}

const char *stateName()
{
    if (!baselineValid)
    {
        return "CAL_REQUIRED";
    }
    if (pressureState == POSITIVE_EVENT)
    {
        return "POSITIVE_EVENT";
    }
    if (pressureState == NEGATIVE_EVENT)
    {
        return "NEGATIVE_EVENT";
    }
    return "IDLE";
}

// t_ms is the read-completion time since MCU boot. Empty fields are unavailable,
// not zero. Comment lines start with # and can be skipped by a CSV reader.
void printSample(unsigned long tMs, bool sampleOk, int16_t raw,
                 const char *state)
{
    Serial.print(tMs);
    Serial.print(',');
    if (sampleOk)
    {
        Serial.print(raw);
    }
    Serial.print(',');
    if (baselineValid)
    {
        Serial.print(baseline);
    }
    Serial.print(',');
    if (sampleOk && baselineValid)
    {
        Serial.print((int32_t)raw - baseline);
    }
    Serial.print(',');
    Serial.print(state);
    Serial.print(',');
    Serial.print(candidateCount);
    Serial.print(',');
    Serial.print(sampleOk ? 1 : 0);
    Serial.print(',');
    Serial.println(baselineValid ? 1 : 0);
}

void invalidateBaseline()
{
    if (pressureState != IDLE)
    {
        Serial.println("# EVENT_ABORTED: incomplete pressure event discarded.");
    }
    baselineValid = false;
    pressureState = IDLE;
    eventStartTime = 0;
    peakValue = 0;
    minimumValue = 0;
    // An interval across a fault or recalibration would be misleading.
    havePreviousCandidate = false;
    previousCandidateTime = 0;
}

bool calibrateBaseline()
{
    invalidateBaseline();
    Serial.println("# CALIBRATING: keep pressure at rest; do not move the syringe.");

    int32_t total = 0;
    int32_t smallest = 32767;
    int32_t largest = -32768;
    for (int i = 0; i < CALIBRATION_SAMPLES; ++i)
    {
        int16_t raw = 0;
        const bool sampleOk = readPressureADC(raw);
        printSample(millis(), sampleOk, raw, "CALIBRATING");
        if (!sampleOk)
        {
            Serial.println("# CALIBRATION_FAILED: ADC read failed; counting disabled. Send z to retry.");
            return false;
        }

        total += raw;
        if (raw < smallest)
        {
            smallest = raw;
        }
        if (raw > largest)
        {
            largest = raw;
        }
        delay(50);
    }

    if (largest - smallest > MAX_CALIBRATION_SPREAD)
    {
        Serial.println("# CALIBRATION_FAILED: signal moved too much; counting disabled. Send z to retry.");
        return false;
    }

    baseline = total / CALIBRATION_SAMPLES;
    baselineValid = true;
    Serial.print("# READY: baseline_raw=");
    Serial.print(baseline);
    Serial.println("; counting enabled. Send z to recalibrate.");
    return true;
}

void processPressure(int16_t raw, unsigned long tMs)
{
    if (!baselineValid)
    {
        return;
    }

    const int32_t difference = (int32_t)raw - baseline;
    if (pressureState == IDLE)
    {
        if (difference > EVENT_THRESHOLD)
        {
            pressureState = POSITIVE_EVENT;
            peakValue = raw;
            eventStartTime = tMs;
            Serial.println("# POSITIVE_PRESSURE_START");
        }
        else if (difference < -EVENT_THRESHOLD)
        {
            pressureState = NEGATIVE_EVENT;
            minimumValue = raw;
            eventStartTime = tMs;
            Serial.println("# NEGATIVE_PRESSURE_START");
        }
        // Keep the calibrated baseline fixed during each measurement run.
        // This leaves resting drift visible in the log; z starts a new baseline.
    }
    else if (pressureState == POSITIVE_EVENT)
    {
        if (raw > peakValue)
        {
            peakValue = raw;
        }
        if (difference < RETURN_THRESHOLD)
        {
            ++candidateCount;
            Serial.print("# CANDIDATE_VENTILATION count=");
            Serial.print(candidateCount);
            Serial.print(", peak_delta_raw=");
            Serial.print((int32_t)peakValue - baseline);
            Serial.print(", duration_ms=");
            Serial.print(tMs - eventStartTime);
            if (havePreviousCandidate)
            {
                Serial.print(", interval_ms=");
                Serial.print(eventStartTime - previousCandidateTime);
            }
            Serial.println();
            previousCandidateTime = eventStartTime;
            havePreviousCandidate = true;
            pressureState = IDLE;
        }
    }
    else if (pressureState == NEGATIVE_EVENT)
    {
        if (raw < minimumValue)
        {
            minimumValue = raw;
        }
        if (difference > -RETURN_THRESHOLD)
        {
            Serial.print("# NEGATIVE_PRESSURE_END min_delta_raw=");
            Serial.print((int32_t)minimumValue - baseline);
            Serial.print(", duration_ms=");
            Serial.println(tMs - eventStartTime);
            pressureState = IDLE;
        }
    }
}

void setup()
{
    Serial.begin(115200);
    const unsigned long start = millis();
    while (!Serial && (millis() - start < 5000))
    {
    }

    Serial.println("# Pressure logger: candidate events only; raw counts are not calibrated pressure.");
    Serial.println("t_ms,raw,baseline,delta,state,candidate_count,sample_ok,baseline_ok");

    WireSensorA.begin();
    pinPeripheral(SENSOR_A_SDA, PIO_SERCOM);
    pinPeripheral(SENSOR_A_SCL, PIO_SERCOM);
    WireSensorA.setClock(100000);
    delay(500);

    // Manual-only calibration: stay in CAL_REQUIRED until the dashboard/user
    // explicitly sends 'z'. A valid baseline then remains fixed until another
    // manual recalibration or an ADC fault invalidates it.
    invalidateBaseline();
    Serial.println("# CAL_REQUIRED: press Calibrate baseline (sends z) when pressure is at rest.");
}

void loop()
{
    bool recalibrate = false;
    while (Serial.available())
    {
        const char command = (char)Serial.read();
        if (command == 'z' || command == 'Z')
        {
            recalibrate = true;
        }
    }
    if (recalibrate)
    {
        calibrateBaseline();
        return;
    }

    int16_t raw = 0;
    const bool sampleOk = readPressureADC(raw);
    const unsigned long tMs = millis();
    if (!sampleOk)
    {
        // Keep the last valid baseline through transient ADC/read failures.
        // The bad sample is discarded, but the user does not have to recalibrate.
        // A new baseline is only created when the user explicitly sends 'z'.
        Serial.println("# ADC_FAULT: sample discarded; previous baseline retained.");
        printSample(tMs, false, 0, stateName());
        delay(200);
        return;
    }

    processPressure(raw, tMs);
    printSample(tMs, true, raw, stateName());
    delay(50);
}
