// K.E.V.I.N. STM32F405 ISOLATED PRESSURE ADC DIAGNOSTIC, Port A UPPER.
// ToF disabled AND physically disconnected. Pressure uses its upper Port A socket.
// Actual carrier v1.0.3; reference PCB is v1.1.0b, so pinout unconfirmed.
// Upper Port A: I2C1 PB7 SDA, PB6 SCL, switched 3.3 V PC9; ToF bench verified.
// MPXV5010GP transducer requires 4.75–5.25 V: the upper 3.3 V connector
// cannot supply a correctly operating pressure transducer by itself.
// This is a MCP3426 I2C/ADC diagnostic only, NOT a calibrated pressure test.

#include <Arduino.h>
#include <Wire.h>
#include "vl6180x.h"

// The existing hardware/firmware has FUNCTIONALLY VERIFIED ToF on Port A upper.
#ifndef KEVIN_TOF_IO_ENABLED
#define KEVIN_TOF_IO_ENABLED 0
#endif
// Pressure I2C power-up requires explicit upper-connector cable & logic verification.
#ifndef KEVIN_PRESSURE_IO_ENABLED
#define KEVIN_PRESSURE_IO_ENABLED 0
#endif
#if KEVIN_PRESSURE_IO_ENABLED
  #if !defined(KEVIN_PRESSURE_A_UPPER_PINOUT_VERIFIED) || KEVIN_PRESSURE_A_UPPER_PINOUT_VERIFIED != 1
    #error "Confirm upper Port A connector/cable GND, 3.3V, SDA/SCL match and are STM32-safe before I2C test."
  #endif
#endif

namespace {
constexpr bool kTofEnabled = KEVIN_TOF_IO_ENABLED != 0;
constexpr bool kPressureEnabled = KEVIN_PRESSURE_IO_ENABLED != 0;
constexpr uint8_t kPressureAddr = 0x68;   // MCP3426
constexpr uint8_t kAdcConfig = 0x88;      // CH1 one-shot, 16 bit, gain x1
constexpr uint32_t kAdcWaitMs = 95;
constexpr uint32_t kPressurePeriodMs = 250;
constexpr uint32_t kTofPeriodMs = 250;
constexpr uint32_t kTofRetryMs = 2000;

// Pressure uses ONLY I2C1 PB7/PB6 on upper Port A; ToF is disabled.
// Upper Port A PC9 previously powered VL6180X successfully.
// No verified 5 V transducer supply is provided; raw counts are ADC-only.
TwoWire tofBus(PB7, PB6);       // SDA, SCL; upper Port A / I2C1
TwoWire &pressureBus = tofBus; // one peripheral, shared alias
vl6180x::Device tof(tofBus);   // inert; ToF I/O compile flag must remain 0
constexpr uint32_t kPressureRail = PC9; // Upper Port A switched 3.3V ONLY
constexpr uint32_t kTofRail = PC9;      // alias pin; ToF function remains OFF

bool pressurePresent = false, pressurePending = false;
bool tofReady = false, baselineValid = false, calibrating = false;
uint32_t adcStarted = 0, lastAdcStarted = 0, lastTof = 0, lastTofAttempt = 0;
uint32_t lastPressureFault = 0, lastPressureProbe = 0, candidateCount = 0, eventStarted = 0;
int32_t baseline = 0, calSum = 0, calMin = 32767, calMax = -32768;
uint16_t calGood = 0, calAttempts = 0;
enum class EventState : uint8_t { Idle, Positive, Negative };
EventState eventState = EventState::Idle;
int32_t eventPeak = 0;

bool ping(TwoWire &bus, uint8_t address) {
  bus.beginTransmission(address);
  return bus.endTransmission() == 0;
}
// When the ADC NACKs, stop polling conversions, discard the stale baseline
// and wait for the existing non-blocking 2-second I2C reconnection check.
// This is a software recovery path; it cannot fix loose wiring or wrong power.
void markPressureOffline() {
  pressurePresent = false;
  pressurePending = false;
  calibrating = false;
  baselineValid = false;
  eventState = EventState::Idle;
  lastPressureProbe = millis();
}
void status() {
  Serial.print("# STATUS pressure_ack=");
  if (kPressureEnabled) {
    const bool responding = ping(pressureBus, kPressureAddr);
    if (!responding) markPressureOffline();
    else pressurePresent = true;
    Serial.print(responding ? 1 : 0);
  } else Serial.print("DISABLED");
  Serial.print(" tof_ack=");
  if (kTofEnabled) Serial.println(ping(tofBus, vl6180x::ADDRESS) ? 1 : 0);
  else Serial.println("DISABLED");
  Serial.println("# I2C ACK does not prove valid measurement");
}
void startCalibration() {
  Serial.println("# CALIBRATION_DISABLED: upper Port A provides no verified 5V transducer supply");
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
  Serial.print("# pressure_adc,t_ms=");
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
  Serial.println(",adc_conversion_valid=1,pressure_calibrated=0");
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
      markPressureOffline();
      Serial.println("# PRESSURE_OFFLINE retrying I2C address 0x68 every 2s");
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
  Serial.println("# KEVIN STM32 PRESSURE ADC ONLY upper Port A v0.2");
  Serial.println("# ToF disabled/disconnected; only MCP3426 address 0x68 on I2C1");
  Serial.println("# WARNING: Upper Port A 3.3V does not establish MPXV5010GP 5V supply");
  Serial.println("# Valid ADC samples do not prove real pressure sensing");
  Serial.println("# Physical v1.0.3 port pinout must be verified before sensor I/O");
  if (!kTofEnabled && !kPressureEnabled) {
    Serial.println("# SAFETY_LOCK ENABLED: USB-only; no sensor GPIO or I2C access");
    return;
  }

  // Only the already bench-verified ToF port (A upper, PB7/PB6, PC9) is
  // activated by default. No pressure pin or Port B power rail is touched.
  if (kTofEnabled) {
    digitalWrite(kTofRail, LOW);
    pinMode(kTofRail, OUTPUT);
    digitalWrite(kTofRail, HIGH);
    delay(50);
    tofBus.begin();
    tofBus.setClock(100000);
    identifyTof();
  } else {
    Serial.println("# TOF_IO_DISABLED");
  }

  // Only enable upper Port A if cable pin order and logic levels are verified.
  if (kPressureEnabled) {
    digitalWrite(kPressureRail, LOW);
    pinMode(kPressureRail, OUTPUT);
    digitalWrite(kPressureRail, HIGH);
    delay(50);
    // Both Port A connectors use I2C1, so share the ONE initialized
    // TwoWire object. Do not begin the STM32 I2C1 peripheral twice.
    if (!kTofEnabled) {
      pressureBus.begin();
      pressureBus.setClock(100000);
    }
    pressurePresent = ping(pressureBus, kPressureAddr);
    lastPressureProbe = millis();
    Serial.println(pressurePresent ? "# PRESSURE_ADC_PRESENT (I2C/ADC diagnostic only)" :
                                     "# PRESSURE_ADC_ABSENT (no data will be reported)");
  } else {
    Serial.println("# PRESSURE_IO_DISABLED upper Port A untouched");
  }
  status();
  Serial.println("# Commands: s=ADC ACK; z=disabled until 5V pressure supply verified; h=help");
}
void loop() {
  if (!kTofEnabled && !kPressureEnabled) {
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
      Serial.println("# Commands: s=ADC ACK; z=disabled in ADC-only mode; h=help");
  }
  if (kPressureEnabled) {
    if (!pressurePresent && millis() - lastPressureProbe >= 2000) {
      lastPressureProbe = millis();
      pressurePresent = ping(pressureBus, kPressureAddr);
      if (pressurePresent) Serial.println("# PRESSURE_ADC_RECONNECTED; readings enabled");
      else Serial.println("# PRESSURE_ADC_ABSENT address 0x68 on I2C1 Port A upper");
    }
    servicePressure(millis());
  }
  if (kTofEnabled) serviceTof(millis()); // may block up to 100 ms
  delay(5);
}
