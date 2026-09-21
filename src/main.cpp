#include <Arduino.h>
#include <Wire.h>
#include "wiring_private.h"

// --------------------------------------------------
// Sensor A2
// --------------------------------------------------

#define SENSOR_A_SDA 11   // PA16
#define SENSOR_A_SCL 13   // PA17

#define MCP3426_ADDR 0x68

TwoWire WireSensorA(&sercom1, SENSOR_A_SDA, SENSOR_A_SCL);

void SERCOM1_Handler()
{
    WireSensorA.onService();
}


// --------------------------------------------------
// Pressure event settings
// --------------------------------------------------

const int EVENT_THRESHOLD  = 200;
const int RETURN_THRESHOLD = 80;

enum PressureState
{
    IDLE,
    POSITIVE_EVENT,
    NEGATIVE_EVENT
};

PressureState pressureState = IDLE;


// --------------------------------------------------
// Measurements
// --------------------------------------------------

int32_t baseline = 0;

int16_t peakValue = 0;
int16_t minimumValue = 0;

unsigned long eventStartTime = 0;


// --------------------------------------------------
// Candidate ventilation tracking
// --------------------------------------------------

unsigned long candidateCount = 0;

unsigned long previousCandidateTime = 0;


// --------------------------------------------------
// Read MCP3426
// --------------------------------------------------

bool readPressureADC(int16_t &rawValue, float &voltage)
{
    // CH1
    // one-shot
    // 16-bit
    // gain x1
    const uint8_t config = 0x88;

    WireSensorA.beginTransmission(MCP3426_ADDR);
    WireSensorA.write(config);

    if (WireSensorA.endTransmission() != 0)
    {
        return false;
    }

    delay(100);

    uint8_t count =
        WireSensorA.requestFrom(MCP3426_ADDR, (uint8_t)3);

    if (count != 3)
    {
        return false;
    }

    uint8_t highByte = WireSensorA.read();
    uint8_t lowByte  = WireSensorA.read();
    uint8_t status   = WireSensorA.read();

    // RDY bit still HIGH = conversion not finished
    if (status & 0x80)
    {
        return false;
    }

    rawValue =
        (int16_t)(((uint16_t)highByte << 8) | lowByte);

    voltage =
        rawValue * (2.048f / 32768.0f);

    return true;
}


// --------------------------------------------------
// Establish resting baseline
// --------------------------------------------------

bool calibrateBaseline()
{
    Serial.println();
    Serial.println("Calibrating baseline...");
    Serial.println("DO NOT move the syringe.");
    Serial.println();

    const int samples = 30;

    int32_t total = 0;
    int goodSamples = 0;

    for (int i = 0; i < samples; i++)
    {
        int16_t raw;
        float voltage;

        if (readPressureADC(raw, voltage))
        {
            total += raw;
            goodSamples++;

            Serial.print(".");
        }

        delay(50);
    }

    Serial.println();

    if (goodSamples == 0)
    {
        return false;
    }

    baseline = total / goodSamples;

    Serial.print("Baseline = ");
    Serial.println(baseline);

    Serial.println();
    Serial.println("Detector ready.");
    Serial.println();

    return true;
}


// --------------------------------------------------
// Setup
// --------------------------------------------------

void setup()
{
    Serial.begin(115200);

    unsigned long start = millis();

    while (!Serial && (millis() - start < 5000))
    {
    }

    Serial.println();
    Serial.println("==================================");
    Serial.println(" Candidate Ventilation Detector");
    Serial.println("==================================");

    WireSensorA.begin();

    pinPeripheral(SENSOR_A_SDA, PIO_SERCOM);
    pinPeripheral(SENSOR_A_SCL, PIO_SERCOM);

    WireSensorA.setClock(100000);

    delay(500);

    if (!calibrateBaseline())
    {
        Serial.println("ERROR: Baseline calibration failed.");
    }
}


// --------------------------------------------------
// Main loop
// --------------------------------------------------

void loop()
{
    int16_t raw;
    float voltage;

    if (!readPressureADC(raw, voltage))
    {
        Serial.println("ADC read failed");
        delay(200);
        return;
    }

    int32_t difference = raw - baseline;


    // ==================================================
    // IDLE
    // ==================================================

    if (pressureState == IDLE)
    {
        // Positive pressure begins
        if (difference > EVENT_THRESHOLD)
        {
            pressureState = POSITIVE_EVENT;

            peakValue = raw;
            eventStartTime = millis();

            Serial.println();
            Serial.println(">>> POSITIVE PRESSURE START");
        }

        // Negative pressure begins
        else if (difference < -EVENT_THRESHOLD)
        {
            pressureState = NEGATIVE_EVENT;

            minimumValue = raw;
            eventStartTime = millis();

            Serial.println();
            Serial.println(">>> NEGATIVE PRESSURE START");
        }

        // Slowly adjust baseline while resting
        else
        {
            baseline =
                (baseline * 99 + raw) / 100;
        }
    }


    // ==================================================
    // POSITIVE PRESSURE EVENT
    // ==================================================

    else if (pressureState == POSITIVE_EVENT)
    {
        if (raw > peakValue)
        {
            peakValue = raw;
        }

        // Returned close to baseline
        if (difference < RETURN_THRESHOLD)
        {
            unsigned long eventEndTime = millis();

            unsigned long duration =
                eventEndTime - eventStartTime;

            candidateCount++;

            Serial.println(">>> POSITIVE PRESSURE END");

            Serial.println();
            Serial.print("CANDIDATE VENTILATION #");
            Serial.println(candidateCount);

            Serial.print("Peak RAW change = +");
            Serial.println(peakValue - baseline);

            Serial.print("Event duration = ");
            Serial.print(duration);
            Serial.println(" ms");

            // Time since previous positive event
            if (previousCandidateTime != 0)
            {
                unsigned long interval =
                    eventStartTime - previousCandidateTime;

                Serial.print("Time since previous candidate = ");
                Serial.print(interval);
                Serial.println(" ms");
            }
            else
            {
                Serial.println(
                    "First candidate event - no previous interval."
                );
            }

            previousCandidateTime = eventStartTime;

            Serial.println();

            pressureState = IDLE;
        }
    }


    // ==================================================
    // NEGATIVE PRESSURE EVENT
    // ==================================================

    else if (pressureState == NEGATIVE_EVENT)
    {
        if (raw < minimumValue)
        {
            minimumValue = raw;
        }

        if (difference > -RETURN_THRESHOLD)
        {
            unsigned long duration =
                millis() - eventStartTime;

            Serial.println(">>> NEGATIVE PRESSURE END");

            Serial.print("Minimum RAW change = ");
            Serial.println(minimumValue - baseline);

            Serial.print("Event duration = ");
            Serial.print(duration);
            Serial.println(" ms");

            Serial.println(
                "Negative event recorded separately."
            );

            Serial.println();

            pressureState = IDLE;
        }
    }

    delay(50);
}