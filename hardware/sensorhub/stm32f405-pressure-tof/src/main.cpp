// K.E.V.I.N. STM32F405 pressure + VL6180X ToF, bench diagnostic only.
// Pressure MCP3426 logic adapted from hardware/sensorhub/pressure-imu/src/main.cpp.
// VL6180X driver supplied by OlympusSixtems/KEVIN (see include/vl6180x.h).
// Photo: RobotPatient SensorHub carrier v1.0.3, NOT the v1.1.0b source schematic.
// SAFE DEFAULT: no sensor rail toggling and no I2C when KEVIN_SENSOR_IO_ENABLED=0.
// Raw ADC counts != calibrated pressure; ToF mm != calibrated compression depth.

#include <Arduino.h>
#include <Wire.h>
#include "vl6180x.h"

#ifndef KEVIN_SENSOR_IO_ENABLED
#define KEVIN_SENSOR_IO_ENABLED 0
#endif
#if KEVIN_SENSOR_IO_ENABLED && (!defined(KEVIN_CARRIER_V103_PINMAP_VERIFIED) || !defined(KEVIN_SENSOR_SUPPLIES_VERIFIED))
#error "Verify v1.0.3 connector pinout, switched rails and pressure/ToF voltage interfaces BEFORE enabling I2C."
#endif

namespace {
constexpr bool kEnabled = KEVIN_SENSOR_IO_ENABLED != 0;
constexpr uint8_t kPressureAddr = 0x68;   // MCP3426
constexpr uint8_t kAdcConfig = 0x88;      // CH1 one-shot, 16 bit, gain x1
constexpr uint32_t kAdcWaitMs = 95;
constexpr uint32_t kPressurePeriodMs = 250;
constexpr uint32_t kTofPeriodMs = 250;
constexpr uint32_t kTofRetryMs = 2000;

// Tentative v1.1.0b pinout ONLY. Do not wire or enable for v1.0.3
// without the actual v1.0.3 schematic/continuity and voltage checks.
TwoWire pressureBus(PB7, PB6); // SDA, SCL; Port A / I2C1 assumed
TwoWire tofBus(PB11, PB10);    // SDA, SCL; Port B / I2C2 assumed
vl6180x::Device tof(tofBus);
constexpr uint32_t kPressureRail = PC9; // tentative: Port A upper
constexpr uint32_t kTofRail = PC8;      // tentative: Port B

bool pressurePresent = false, pressurePending = false;
bool tofReady = false, baselineValid = false, calibrating = false;
uint32_t adcStarted = 0, lastAdcStarted = 0, lastTof = 0, lastTofAttempt = 0;
uint32_t lastPressureFault = 0, candidateCount = 0, eventStarted = 0;
int32_t baseline = 0, calSum = 0, calMin = 32767, calMax = -32768;
uint16_t calGood = 0, calAttempts = 0;
enum class EventState : uint8_t { Idle, Positive, Negative };
EventState eventState = EventState::Idle;
int32_t eventPeak = 0;

bool ping(TwoWire &bus, uint8_t address) {
  bus.beginTransmission(address);
  return bus.endTransmission() == 0;
}
void status() {
  Serial.print("# STATUS pressure_ack=");
  Serial.print(ping(pressureBus, kPressureAddr) ? 1 : 0);
  Serial.print(" tof_ack=");
  Serial.println(ping(tofBus, vl6180x::ADDRESS) ? 1 : 0);
  Serial.println("# I2C ACK does not prove valid measurement");
}
void startCalibration() {
  if (!pressurePresent) {
    Serial.println("# CALIBRATION_SKIPPED MCP3426 not present at startup");
    return;
  }
  calibrating = true;
  calSum = 0; calMin = 32767; calMax = -32768;
  calGood = 0; calAttempts = 0;
  eventState = EventState::Idle;
  Serial.println("# CALIBRATING pressure at rest, ToF continues");
}
void badCalibrationAttempt() {
  if (!calibrating) return;
  if (++calAttempts >= 45) {
    calibrating = false;
    Serial.println("# CALIBRATION_FAILED too few valid samples; previous baseline retained");
  }
}
void calibrationSample(int16_t raw) {
  ++calAttempts;
  ++calGood;
  calSum += raw;
  if (raw < calMin) calMin = raw;
  if (raw > calMax) calMax = raw;
  if (calGood < 30) {
    if (calAttempts >= 45) {
      calibrating = false;
      Serial.println("# CALIBRATION_FAILED too many attempts; previous baseline retained");
    }
    return;
  }
  calibrating = false;
  if (calMax - calMin > 80) {
    Serial.println("# CALIBRATION_FAILED movement exceeded 80 ADC counts; baseline retained");
    return;
  }
  baseline = calSum / 30;
  baselineValid = true;
  Serial.print("# CALIBRATION_OK baseline_adc=");
  Serial.println(baseline);
}
void trackPressure(int16_t raw, uint32_t t) {
  if (!baselineValid || calibrating) return;
  const int32_t delta = static_cast<int32_t>(raw) - baseline;
  if (eventState == EventState::Idle) {
    if (delta > 200 || delta < -200) {
      eventState = delta > 0 ? EventState::Positive : EventState::Negative;
      eventStarted = t;
      eventPeak = delta;
      Serial.println(delta > 0 ? "# PRESSURE_POSITIVE_START" : "# PRESSURE_NEGATIVE_START");
    }
  } else if (eventState == EventState::Positive) {
    if (delta > eventPeak) eventPeak = delta;
    if (delta < 80) {
      ++candidateCount;
      Serial.print("# PRESSURE_POSITIVE_END candidate=");
      Serial.print(candidateCount);
      Serial.print(" peak_delta_adc=");
      Serial.print(eventPeak);
      Serial.print(" duration_ms=");
      Serial.println(t - eventStarted);
      eventState = EventState::Idle;
    }
  } else {
    if (delta < eventPeak) eventPeak = delta;
    if (delta > -80) {
      Serial.print("# PRESSURE_NEGATIVE_END min_delta_adc=");
      Serial.print(eventPeak);
      Serial.print(" duration_ms=");
      Serial.println(t - eventStarted);
      eventState = EventState::Idle;
    }
  }
}
void printPressure(int16_t raw) {
  Serial.print("# pressure,t_ms=");
  Serial.print(millis());
  Serial.print(",raw_adc=");
  Serial.print(raw);
  Serial.print(",baseline_adc=");
  if (baselineValid) Serial.print(baseline);
  Serial.print(",delta_adc=");
  if (baselineValid) Serial.print(static_cast<int32_t>(raw) - baseline);
  Serial.print(",calibrating=");
  Serial.print(calibrating ? 1 : 0);
  Serial.print(",candidate_count=");
  Serial.print(candidateCount);
  Serial.println(",valid=1");
}
void pressureFault(const char *reason) {
  if (millis() - lastPressureFault < 2000) return;
  Serial.print("# PRESSURE_FAULT reason=");
  Serial.println(reason);
  lastPressureFault = millis();
}
// Two-phase MCP3426 acquisition: do other work while ADC converts.
// If no ADC is present at boot, no pressure values are fabricated.
void servicePressure(uint32_t now) {
  if (!pressurePresent) return;
  if (!pressurePending) {
    if (now - lastAdcStarted < kPressurePeriodMs) return;
    lastAdcStarted = now;
    pressureBus.beginTransmission(kPressureAddr);
    pressureBus.write(kAdcConfig);
    if (pressureBus.endTransmission() != 0) {
      pressureFault("config_write_nack");
      badCalibrationAttempt();
      return;
    }
    pressurePending = true;
    adcStarted = millis();
    return;
  }
  if (now - adcStarted < kAdcWaitMs) return;
  pressurePending = false;
  const uint8_t count = pressureBus.requestFrom(kPressureAddr, static_cast<uint8_t>(3));
  if (count != 3) {
    while (pressureBus.available()) pressureBus.read();
    pressureFault("short_read");
    badCalibrationAttempt();
    return;
  }
  const uint8_t hi = pressureBus.read();
  const uint8_t lo = pressureBus.read();
  const uint8_t config = pressureBus.read();
  if ((config & 0x80) || (config & 0x7F) != (kAdcConfig & 0x7F)) {
    pressureFault("adc_not_ready_or_config_mismatch");
    badCalibrationAttempt();
    return;
  }
  const int16_t raw = static_cast<int16_t>((static_cast<uint16_t>(hi) << 8) | lo);
  if (calibrating) calibrationSample(raw);
  else trackPressure(raw, now);
  printPressure(raw);
}
void identifyTof() {
  lastTofAttempt = millis();
  if (!tof.present()) {
    Serial.println("# TOF_ABSENT I2C 0x29");
    tofReady = false;
    return;
  }
  vl6180x::Identity id;
  if (!tof.readIdentity(id) || id.modelId != vl6180x::EXPECTED_MODEL_ID) {
    Serial.println("# TOF_BAD_ID expected 0xB4");
    tofReady = false;
    return;
  }
  if (!tof.init()) {
    Serial.println("# TOF_INIT_FAILED");
    tofReady = false;
    return;
  }
  Serial.println("# TOF_READY VL6180X; raw distance only");
  tofReady = true;
}
void serviceTof(uint32_t now) {
  if (!tofReady) {
    if (now - lastTofAttempt >= kTofRetryMs) identifyTof();
    return;
  }
  if (now - lastTof < kTofPeriodMs) return;
  lastTof = now;
  vl6180x::Range range;
  if (!tof.measure(range, 100)) {
    Serial.println("# TOF_READ_FAILED; will retry identification");
    tofReady = false;
    lastTofAttempt = now;
    return;
  }
  Serial.print("# tof,t_ms=");
  Serial.print(millis());
  Serial.print(",raw_mm=");
  Serial.print(range.mm);
  Serial.print(",err=");
  Serial.print(range.errorCode);
  Serial.print(",valid=");
  Serial.println(range.errorCode == 0 ? 1 : 0);
}
} // namespace

void setup() {
  Serial.begin(115200);
  const uint32_t started = millis();
  while (!Serial && millis() - started < 3000) delay(10);
  Serial.println("# KEVIN STM32 PRESSURE + TOF v0.1, diagnostic");
  Serial.println("# Photo carrier v1.0.3; reference schematic is v1.1.0b");
  if (!kEnabled) {
    Serial.println("# SAFETY_LOCK ENABLED: USB-only; no rail GPIO or I2C access");
    return;
  }

  // DANGER if enabled without verification. Tentative v1.1.0b mapping.
  digitalWrite(kPressureRail, LOW);
  pinMode(kPressureRail, OUTPUT);
  digitalWrite(kTofRail, LOW);
  pinMode(kTofRail, OUTPUT);
  digitalWrite(kPressureRail, HIGH);
  digitalWrite(kTofRail, HIGH);
  delay(50);

  pressureBus.begin();
  pressureBus.setClock(100000);
  tofBus.begin();
  tofBus.setClock(100000);
  pressurePresent = ping(pressureBus, kPressureAddr);
  status();
  Serial.println(pressurePresent ? "# PRESSURE_ADC_PRESENT send z for zero calibration" :
                                   "# PRESSURE_ADC_ABSENT (no data will be reported)");
  identifyTof();
  Serial.println("# Commands: s=address ACKs; z=pressure zero calibration; h=help");
}
void loop() {
  if (!kEnabled) {
    static uint32_t heartbeatMs = 0;
    if (millis() - heartbeatMs >= 2000) {
      Serial.println("# SAFETY_LOCK_HEARTBEAT");
      heartbeatMs = millis();
    }
    delay(25);
    return;
  }
  while (Serial.available()) {
    const char c = static_cast<char>(Serial.read());
    if (c == 's' || c == 'S') status();
    if (c == 'z' || c == 'Z') startCalibration();
    if (c == 'h' || c == 'H')
      Serial.println("# Commands: s=address ACKs; z=calibrate pressure; h=help");
  }
  servicePressure(millis());
  serviceTof(millis()); // may block up to 100 ms
  delay(5);
}
