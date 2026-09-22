// Compile this file with tests/stubs on the include path, outside PlatformIO.
// It exercises the actual firmware through simulated ADC and serial inputs.
#include <Arduino.h>
#include <Wire.h>
#include <algorithm>
#include <cassert>
#include <iostream>

uint32_t testMillis = 0;
TestSerial Serial;
TestSercom sercom1;
#include "../src/main.cpp"

void resetTest()
{
    testMillis = 0;
    Serial.output.str("");
    Serial.output.clear();
    Serial.input.clear();
    WireSensorA.conversions.clear();
    WireSensorA.response.clear();
    pressureState = IDLE;
    baselineValid = false;
    baseline = 0;
    peakValue = 0;
    minimumValue = 0;
    eventStartTime = 0;
    candidateCount = 0;
    previousCandidateTime = 0;
    havePreviousCandidate = false;
}

void queueCalibration(int16_t resting = 2540)
{
    for (int i = 0; i < 30; ++i)
    {
        WireSensorA.conversions.emplace_back(resting);
    }
}

void makeReady()
{
    resetTest();
    queueCalibration();
    setup();
    assert(baselineValid && baseline == 2540 && candidateCount == 0);
}

void sample(int16_t raw)
{
    WireSensorA.conversions.emplace_back(raw);
    loop();
}

bool outputContains(const std::string &text)
{
    return Serial.output.str().find(text) != std::string::npos;
}

void assertCsvShape()
{
    std::istringstream rows(Serial.output.str());
    std::string row;
    while (std::getline(rows, row))
    {
        if (row.empty() || row[0] == '#') continue;
        assert(std::count(row.begin(), row.end(), ',') == 7);
    }
}

int main()
{
    // Successful startup logs calibration and normal samples with distinct flags.
    makeReady();
    sample(2542);
    assert(outputContains(",2540,,,CALIBRATING,0,1,0"));
    assert(outputContains(",2542,2540,2,IDLE,0,1,1"));
    assertCsvShape();

    // A single read failure, even after 29 good samples, rejects calibration.
    resetTest();
    for (int i = 0; i < 29; ++i) WireSensorA.conversions.emplace_back(2540);
    WireSensorA.conversions.emplace_back(0, 0x08, 3, 2);
    setup();
    assert(!baselineValid && outputContains("# CALIBRATION_FAILED"));
    sample(3100);
    sample(2540);
    assert(candidateCount == 0 && pressureState == IDLE);
    assert(outputContains(",3100,,,CAL_REQUIRED,0,1,0"));
    assertCsvShape();

    // An unstable startup must not zero itself on the average of a pressure pulse.
    resetTest();
    for (int i = 0; i < 29; ++i) WireSensorA.conversions.emplace_back(2540);
    WireSensorA.conversions.emplace_back(2621);
    setup();
    assert(!baselineValid && outputContains("signal moved too much"));

    // A sustained positive excursion is counted only once after recovery.
    makeReady();
    sample(3000);
    sample(3100);
    sample(3050);
    assert(candidateCount == 0 && pressureState == POSITIVE_EVENT);
    sample(2540);
    sample(2540);
    assert(candidateCount == 1 && pressureState == IDLE);
    assert(outputContains("peak_delta_raw=560, duration_ms=450"));
    assert(!outputContains("interval_ms="));
    sample(3000);
    sample(2540);
    assert(candidateCount == 2 && outputContains("interval_ms=750"));
    assertCsvShape();

    // Hysteresis keeps the same event active between start and return thresholds.
    makeReady();
    sample(2790);
    sample(2640);
    assert(pressureState == POSITIVE_EVENT && candidateCount == 0);
    sample(2610);
    assert(pressureState == IDLE && candidateCount == 1);

    // Negative excursions remain separate from candidate ventilation counts.
    makeReady();
    sample(2100);
    sample(2000);
    sample(2540);
    assert(candidateCount == 0 && pressureState == IDLE);
    assert(outputContains("# NEGATIVE_PRESSURE_END min_delta_raw=-540"));

    // A failed read aborts the active event; recovery alone cannot resume counting.
    makeReady();
    sample(3000);
    WireSensorA.conversions.emplace_back(0, 0x08, 3, 2);
    loop();
    assert(!baselineValid && pressureState == IDLE && candidateCount == 0);
    assert(outputContains("# EVENT_ABORTED"));
    assert(outputContains(",,,,CAL_REQUIRED,0,0,0"));
    sample(2540);
    sample(3100);
    sample(2540);
    assert(candidateCount == 0);
    Serial.input.push_back('z');
    queueCalibration();
    loop();
    assert(baselineValid);
    sample(3100);
    sample(2540);
    assert(candidateCount == 1 && !outputContains("interval_ms="));
    assertCsvShape();

    // Partial frames, busy conversions and unexpected ADC modes are all invalid.
    const TestConversion badFrames[] = {
        TestConversion(3000, 0x08, 2),
        TestConversion(3000, 0x88),
        TestConversion(3000, 0x04)
    };
    for (const TestConversion &frame : badFrames)
    {
        makeReady();
        WireSensorA.conversions.push_back(frame);
        loop();
        assert(!baselineValid && candidateCount == 0);
        assert(outputContains(",,,,CAL_REQUIRED,0,0,0"));
    }

    // z preserves completed counts, discards an active event and resets intervals.
    makeReady();
    sample(3100);
    sample(2540);
    sample(3100);
    Serial.input.push_back('Z');
    Serial.input.push_back('\r');
    Serial.input.push_back('\n');
    queueCalibration(2530);
    loop();
    assert(baselineValid && baseline == 2530 && candidateCount == 1);
    assert(!havePreviousCandidate && pressureState == IDLE);
    sample(3100);
    sample(2530);
    assert(candidateCount == 2 && !outputContains("interval_ms="));

    // Resting drift stays visible relative to the fixed measurement-run baseline.
    makeReady();
    for (int i = 0; i < 100; ++i) sample(2590);
    assert(baseline == 2540 && candidateCount == 0);
    assert(outputContains(",2590,2540,50,IDLE,0,1,1"));
    assertCsvShape();

    std::cout << "12 host scenarios passed. Hardware acquisition and USB require a board test.\n";
}
