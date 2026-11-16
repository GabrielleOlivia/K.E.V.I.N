#include <Arduino.h>
#include <Wire.h>
#include "wiring_private.h"

// Integrated pressure + dual BHI360 identification; manikin research only.
// Pressure measurements are ADC counts, not calibrated airway pressure.

// Sensor A2: Feather M0 Express variant indices for PA16 and PA17.
#define SENSOR_A_SDA 11
#define SENSOR_A_SCL 13
#define MCP3426_ADDR 0x68
#define SENSOR_B_SDA 28
#define SENSOR_B_SCL 39
#define BHI360_ADDR 0x29
#define BHI360_FUSER2_ID_REG 0x1C
#define BHI360_CHIP_ID_REG 0x2B
#define BHI360_REVISION_REG 0x1D
#define BHI360_BOOT_STATUS_REG 0x25
#define BHI360_ERROR_REG 0x2E

// A / SERCOM1 serves BOTH pressure MCP3426 (0x68) and CHEST BHI360 (0x29).
// B / SERCOM2 serves HEAD BHI360 (0x29). Identical BHI addresses are fine
// because HEAD is on a separate hardware bus.
TwoWire WireSensorA(&sercom1, SENSOR_A_SDA, SENSOR_A_SCL);
TwoWire WireSensorB(&sercom2, SENSOR_B_SDA, SENSOR_B_SCL);

void SERCOM1_Handler() { WireSensorA.onService(); }
void SERCOM2_Handler() { WireSensorB.onService(); }

constexpr uint8_t EXPECTED_FUSER2_ID = 0x89;
constexpr uint8_t EXPECTED_CHIP_ID = 0x7A;
constexpr uint32_t IMU_PROBE_INTERVAL_MS = 2000;

struct ImuStatus {
    bool identified;
    uint8_t revision;
    uint8_t bootStatus;
    uint8_t errorCode;
    bool statusReadable;
};

ImuStatus chestImu = {};
ImuStatus headImu = {};
uint32_t lastImuProbeMs = 0;

bool pinsMatch(uint8_t index, uint32_t port, uint32_t pin)
{
    return static_cast<uint32_t>(g_APinDescription[index].ulPort) == port &&
           g_APinDescription[index].ulPin == pin;
}

// Read-only probe: register-pointer selection is the only I2C write.
// Never reset the BHI360 or upload fusion firmware from this project.
bool readImuRegister(TwoWire &bus, uint8_t reg, uint8_t &value)
{
    bus.beginTransmission(BHI360_ADDR);
    bus.write(reg);
    if (bus.endTransmission(false) != 0) return false;

    if (bus.requestFrom(BHI360_ADDR, static_cast<uint8_t>(1),
                        static_cast<uint8_t>(true)) != 1)
    {
        while (bus.available()) bus.read();
        return false;
    }
    if (!bus.available()) return false;
    value = static_cast<uint8_t>(bus.read());
    return true;
}

void probeImu(TwoWire &bus, const char *label, ImuStatus &status)
{
    status = {};
    uint8_t fuser = 0;
    uint8_t chip = 0;
    const bool idOk = readImuRegister(bus, BHI360_FUSER2_ID_REG, fuser) &&
                      readImuRegister(bus, BHI360_CHIP_ID_REG, chip) &&
                      fuser == EXPECTED_FUSER2_ID &&
                      chip == EXPECTED_CHIP_ID;
    status.identified = idOk;
    Serial.print("# IMU,"); Serial.print(label);
    Serial.print(",identified="); Serial.print(idOk ? 1 : 0);
    if (!idOk)
    {
        Serial.println(",motion=UNAVAILABLE (identity not verified)");
        return;
    }

    uint8_t rev = 0, boot = 0, error = 0;
    const bool detailOk =
        readImuRegister(bus, BHI360_REVISION_REG, rev) &&
        readImuRegister(bus, BHI360_BOOT_STATUS_REG, boot) &&
        readImuRegister(bus, BHI360_ERROR_REG, error);
    status.statusReadable = detailOk;
    if (detailOk)
    {
        status.revision = rev;
        status.bootStatus = boot;
        status.errorCode = error;
        Serial.print(",revision=0x"); Serial.print(rev, HEX);
        Serial.print(",boot=0x"); Serial.print(boot, HEX);
        Serial.print(",error=0x"); Serial.print(error, HEX);
    }
    else
    {
        Serial.print(",status_read=FAILED");
    }
    Serial.println(",motion=NOT_INITIALIZED");
}

void probeBothImus()
{
    probeImu(WireSensorA, "CHEST", chestImu);
    probeImu(WireSensorB, "HEAD", headImu);
    lastImuProbeMs = millis();
}

// Provisional raw-count thresholds for this bench setup, not clinical limits.
const int EVENT_THRESHOLD = 200;
const int RETURN_THRESHOLD = 80;
const int CALIBRATION_SAMPLES = 30;
const int MAX_CALIBRATION_ATTEMPTS = 45;
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

// Extra unified machine-readable status row. Keeping the original pressure CSV
// unchanged means the existing pressure dashboard can continue to ignore '#'
// lines. The last (neck_angle_deg) field is deliberately EMPTY: neither BHI360
// is running fusion firmware yet. Never substitute a fake zero angle.
void printJoinedSample(unsigned long tMs, bool sampleOk, int16_t raw,
                       const char *state)
{
    Serial.print("# JOIN,"); Serial.print(tMs);
    Serial.print(',');
    if (sampleOk) Serial.print(raw);
    Serial.print(',');
    if (sampleOk && baselineValid) Serial.print(static_cast<int32_t>(raw) - baseline);
    Serial.print(','); Serial.print(state);
    Serial.print(','); Serial.print(candidateCount);
    Serial.print(','); Serial.print(sampleOk ? 1 : 0);
    Serial.print(','); Serial.print(baselineValid ? 1 : 0);
    Serial.print(','); Serial.print(chestImu.identified ? 1 : 0);
    Serial.print(','); Serial.print(headImu.identified ? 1 : 0);
    Serial.print(','); // neck_angle_deg is unavailable until genuine fusion works
    Serial.println();
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
    printJoinedSample(tMs, sampleOk, raw, state);
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
    // Do NOT throw away a known-good baseline just because a new calibration
    // attempt has a missed ADC sample. Only replace the baseline after a
    // complete, stable calibration succeeds.
    const bool hadBaseline = baselineValid;
    const int32_t previousBaseline = baseline;

    pressureState = IDLE;
    eventStartTime = 0;
    peakValue = 0;
    minimumValue = 0;
    havePreviousCandidate = false;
    previousCandidateTime = 0;

    Serial.println("# CALIBRATING: keep pressure at rest; do not move the syringe.");

    int32_t total = 0;
    int32_t smallest = 32767;
    int32_t largest = -32768;
    int goodSamples = 0;
    int attempts = 0;

    while (goodSamples < CALIBRATION_SAMPLES &&
           attempts < MAX_CALIBRATION_ATTEMPTS)
    {
        ++attempts;

        int16_t raw = 0;
        const bool sampleOk = readPressureADC(raw);

        // During a re-calibration attempt, preserve/show the old baseline until
        // the new baseline has actually passed all checks.
        printSample(millis(), sampleOk, raw, "CALIBRATING");

        if (!sampleOk)
        {
            Serial.println("# CALIBRATION_NOTE: ADC sample missed; retrying.");
            delay(50);
            continue;
        }

        total += raw;
        ++goodSamples;

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

    if (goodSamples < CALIBRATION_SAMPLES)
    {
        baselineValid = hadBaseline;
        baseline = previousBaseline;
        Serial.println(
            hadBaseline
                ? "# CALIBRATION_FAILED: not enough good ADC samples; previous baseline retained."
                : "# CALIBRATION_FAILED: not enough good ADC samples; no baseline available."
        );
        return false;
    }

    if (largest - smallest > MAX_CALIBRATION_SPREAD)
    {
        baselineValid = hadBaseline;
        baseline = previousBaseline;
        Serial.println(
            hadBaseline
                ? "# CALIBRATION_FAILED: signal moved too much; previous baseline retained."
                : "# CALIBRATION_FAILED: signal moved too much; no baseline available."
        );
        return false;
    }

    baseline = total / CALIBRATION_SAMPLES;
    baselineValid = true;

    Serial.print("# READY: baseline_raw=");
    Serial.print(baseline);
    Serial.println("; baseline locked until you press Calibrate baseline again.");

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

    Serial.println("# KEVIN PRESSURE + DUAL IMU v0.1 — ID ONLY; no fusion firmware writes");
    Serial.println("# Pressure sensor: MCP3426 @0x68, A2; CHEST @0x29, A1; HEAD @0x29, B1");
    Serial.println("# Candidate pressure events only, not infant ventilation or calibrated pressure");
    Serial.println("t_ms,raw,baseline,delta,state,candidate_count,sample_ok,baseline_ok");
    Serial.println("# JOIN_FIELDS,t_ms,raw,delta,state,candidate_count,sample_ok,baseline_ok,chest_identified,head_identified,neck_angle_deg");

    if (!pinsMatch(SENSOR_A_SDA, PORTA, 16) ||
        !pinsMatch(SENSOR_A_SCL, PORTA, 17) ||
        !pinsMatch(SENSOR_B_SDA, PORTA, 12) ||
        !pinsMatch(SENSOR_B_SCL, PORTA, 13))
    {
        Serial.println("# FATAL PINMAP_MISMATCH: stopping before any bus operations");
        while (true) delay(1000);
    }

    WireSensorA.begin();
    pinPeripheral(SENSOR_A_SDA, PIO_SERCOM);
    pinPeripheral(SENSOR_A_SCL, PIO_SERCOM);
    WireSensorA.setClock(100000);

    WireSensorB.begin();
    pinPeripheral(SENSOR_B_SDA, PIO_SERCOM);
    pinPeripheral(SENSOR_B_SCL, PIO_SERCOM);
    WireSensorB.setClock(100000);

    delay(200);
    probeBothImus();
    Serial.println("# Commands: z=calibrate pressure at rest; p=probe IMUs; h=help");

    // Manual-only calibration: stay in CAL_REQUIRED until the dashboard/user
    // explicitly sends 'z'. A valid baseline then remains fixed until another
    // manual recalibration or an ADC fault invalidates it.
    invalidateBaseline();
    Serial.println("# CAL_REQUIRED: press Calibrate baseline (sends z) when pressure is at rest.");
}

void loop()
{
    bool recalibrate = false;
    bool forceProbe = false;
    while (Serial.available())
    {
        const char command = static_cast<char>(Serial.read());
        if (command == 'z' || command == 'Z') recalibrate = true;
        if (command == 'p' || command == 'P') forceProbe = true;
        if (command == 'h' || command == 'H')
        {
            Serial.println("# z=calibrate pressure at rest; p=read-only IMU probe; h=help");
            Serial.println("# IMU orientation NOT available. 'identified=1' does not mean motion works.");
        }
    }
    if (forceProbe ||
        static_cast<uint32_t>(millis() - lastImuProbeMs) >= IMU_PROBE_INTERVAL_MS)
    {
        probeBothImus();
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
