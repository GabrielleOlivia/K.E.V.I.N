// K.E.V.I.N.: independent I2C buses, SAMD21 Sensor A2 pressure + Sensor B2 VL6180X.
// Bench diagnostics only: ADC counts are NOT calibrated pressure; mm are raw ToF distances.
// Wiring changes only with USB disconnected. Pressure MCP3426 0x68 on SERCOM1,
// VL6180X 0x29 on SERCOM2. No IMUs connected.
#include <Arduino.h>
#include <Wire.h>
#include "wiring_private.h"
#include "vl6180x.h"

namespace {
constexpr uint8_t kPressureSda = 11; // Feather M0 index for PA16, SERCOM1
constexpr uint8_t kPressureScl = 13; // Feather M0 index for PA17, SERCOM1
constexpr uint8_t kTofSda = 28;     // Feather M0 index for PA12, SERCOM2
constexpr uint8_t kTofScl = 39;     // Feather M0 index for PA13, SERCOM2
constexpr uint8_t kPressureAddr = 0x68;
constexpr uint8_t kPressureConfig = 0x88; // MCP3426 CH1 one-shot, 16bit, gain 1
constexpr uint32_t kPressurePeriodMs = 250;
constexpr uint32_t kPressureWaitMs = 110;
constexpr uint32_t kTofPeriodMs = 250;
constexpr uint32_t kTofTimeoutMs = 100;
constexpr uint32_t kRetryMs = 2000;

TwoWire pressureBus(&sercom1, kPressureSda, kPressureScl);
TwoWire tofBus(&sercom2, kTofSda, kTofScl);
vl6180x::Device tof(tofBus);

bool pressurePresent = false;
bool pressurePending = false;
bool tofReady = false;
bool streaming = true;
uint32_t pressureStartedMs = 0, lastPressureStartMs = 0, lastPressureProbeMs = 0;
uint32_t lastTofMs = 0, lastTofProbeMs = 0;

bool pinIs(uint8_t index, uint32_t port, uint32_t pin) {
  return static_cast<uint32_t>(g_APinDescription[index].ulPort) == port &&
         g_APinDescription[index].ulPin == pin;
}

bool ping(TwoWire &bus, uint8_t address) {
  bus.beginTransmission(address);
  return bus.endTransmission(true) == 0;
}

void scanBus(TwoWire &bus, const char *name) {
  Serial.print("# SCAN_START bus=");
  Serial.println(name);
  uint8_t found = 0;
  for (uint8_t addr = 0x03; addr <= 0x77; ++addr) {
    bus.beginTransmission(addr);
    if (bus.endTransmission(true) == 0) {
      Serial.print("# SCAN_FOUND bus=");
      Serial.print(name);
      Serial.print(" address=0x");
      if (addr < 16) Serial.print('0');
      Serial.println(addr, HEX);
      ++found;
    }
  }
  Serial.print("# SCAN_END bus=");
  Serial.print(name);
  Serial.print(" count=");
  Serial.println(found);
}
void status() {
  Serial.print("# STATUS pressure_A2_ack=");
  Serial.print(ping(pressureBus, kPressureAddr) ? 1 : 0);
  Serial.print(" tof_B2_ack=");
  Serial.print(ping(tofBus, vl6180x::ADDRESS) ? 1 : 0);
  Serial.print(" tof_initialized=");
  Serial.println(tofReady ? 1 : 0);
}

void pressureFault(const char *reason) {
  pressurePending = false;
  pressurePresent = false;
  lastPressureProbeMs = millis();
  Serial.print("# PRESSURE_FAULT reason=");
  Serial.println(reason);
}

// Emits 1 raw ADC row after MCP3426 conversion has completed.
// Invalid, stale and partial reads are never silently interpreted as zero.
void servicePressure(uint32_t now) {
  if (!pressurePresent) {
    if (now - lastPressureProbeMs >= kRetryMs) {
      lastPressureProbeMs = now;
      pressurePresent = ping(pressureBus, kPressureAddr);
      if (pressurePresent) Serial.println("# PRESSURE_RECONNECTED A2 0x68");
      else Serial.println("# PRESSURE_ABSENT A2 0x68");
    }
    return;
  }
  if (pressurePending) {
    if (now - pressureStartedMs < kPressureWaitMs) return;
    pressurePending = false;
    const uint8_t count = pressureBus.requestFrom(kPressureAddr, static_cast<uint8_t>(3));
    if (count != 3) {
      while (pressureBus.available()) pressureBus.read();
      Serial.println("# PRESSURE_SAMPLE_INVALID reason=short_read");
      // A failed read can be transient; reconfirm address before retry.
      if (!ping(pressureBus, kPressureAddr)) pressureFault("address_nack");
      return;
    }
    const uint8_t hi = pressureBus.read();
    const uint8_t lo = pressureBus.read();
    const uint8_t config = pressureBus.read();
    if ((config & 0x80) != 0) {
      Serial.println("# PRESSURE_SAMPLE_INVALID reason=adc_busy");
      return;
    }
    if ((config & 0x7F) != (kPressureConfig & 0x7F)) {
      Serial.println("# PRESSURE_SAMPLE_INVALID reason=config_mismatch");
      return;
    }
    const int16_t raw = static_cast<int16_t>((static_cast<uint16_t>(hi) << 8) | lo);
    Serial.print("# pressure,t_ms=");
    Serial.print(millis());
    Serial.print(",raw_adc=");
    Serial.print(raw);
    Serial.println(",valid=1,pressure_calibrated=0");
    return;
  }

  if (now - lastPressureStartMs < kPressurePeriodMs) return;
  lastPressureStartMs = now;
  pressureBus.beginTransmission(kPressureAddr);
  pressureBus.write(kPressureConfig);
  if (pressureBus.endTransmission(true) != 0) {
    pressureFault("config_write_nack");
    return;
  }
  pressureStartedMs = millis();
  pressurePending = true;
}

void identifyTof() {
  lastTofProbeMs = millis();
  tofReady = false;
  if (!tof.present()) {
    Serial.println("# TOF_ABSENT B2 0x29");
    return;
  }
  vl6180x::Identity identity;
  if (!tof.readIdentity(identity)) {
    Serial.println("# TOF_ID_READ_FAILED B2");
    return;
  }
  Serial.print("# TOF_MODEL_ID value=0x");
  if (identity.modelId < 16) Serial.print('0');
  Serial.print(identity.modelId, HEX);
  Serial.print(" expected=0xB4 identified=");
  Serial.println(identity.modelId == vl6180x::EXPECTED_MODEL_ID ? 1 : 0);

  // A different I2C device might also respond at 0x29. Do not write to it.
  if (identity.modelId != vl6180x::EXPECTED_MODEL_ID) {
    Serial.println("# TOF_WRONG_DEVICE do_not_initialize");
    return;
  }
  if (!tof.init()) {
    Serial.println("# TOF_INIT_FAILED B2");
    return;
  }
  tofReady = true;
  lastTofMs = millis();
  Serial.println("# TOF_READY B2 live ranging");
}

void serviceTof(uint32_t now) {
  if (!tofReady) {
    if (now - lastTofProbeMs >= kRetryMs) identifyTof();
    return;
  }
  if (now - lastTofMs < kTofPeriodMs) return;
  lastTofMs = now;
  vl6180x::Range range;
  if (!tof.measure(range, kTofTimeoutMs)) {
    Serial.println("# TOF_READ_FAILED B2, retry in 2s");
    tofReady = false;
    lastTofProbeMs = millis();
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

void SERCOM1_Handler() { pressureBus.onService(); }
void SERCOM2_Handler() { tofBus.onService(); }

void setup() {
  Serial.begin(115200);
  const uint32_t started = millis();
  while (!Serial && millis() - started < 4000) delay(10);

  Serial.println("# KEVIN SAMD21 PRESSURE A2 + VL6180X TOF B2 v0.2");
  Serial.println("# Two independent I2C buses; pressure=0x68 on A, ToF=0x29 on B");
  Serial.println("# Raw ADC counts NOT calibrated pressure; raw ToF mm NOT compression depth");
  Serial.println("# MPXV5010GP transducer supply must be independently verified for accurate pressure sensing");
  if (!pinIs(kPressureSda, PORTA, 16) || !pinIs(kPressureScl, PORTA, 17) ||
      !pinIs(kTofSda, PORTA, 12) || !pinIs(kTofScl, PORTA, 13)) {
    Serial.println("# FATAL PINMAP_MISMATCH: neither I2C bus started");
    while (true) delay(1000);
  }
  pressureBus.begin();
  pinPeripheral(kPressureSda, PIO_SERCOM);
  pinPeripheral(kPressureScl, PIO_SERCOM);
  pressureBus.setClock(100000);

  tofBus.begin();
  pinPeripheral(kTofSda, PIO_SERCOM);
  pinPeripheral(kTofScl, PIO_SERCOM);
  tofBus.setClock(100000);

  delay(200);
  pressurePresent = ping(pressureBus, kPressureAddr);
  lastPressureProbeMs = millis();
  Serial.println(pressurePresent ? "# PRESSURE_PRESENT A2 0x68" :
                                   "# PRESSURE_ABSENT A2 0x68");
  identifyTof();
  status();
  Serial.println("# Commands: s=I2C status; i=scan both buses; p=pause/resume samples; h=help");
}

void loop() {
  while (Serial.available()) {
    const char c = static_cast<char>(Serial.read());
    if (c == 's' || c == 'S') status();
    else if (c == 'i' || c == 'I') {
      // Address-only scan. Does not read/write sensor registers.
      // Pause user-requested streaming around bus probing; device conversion
      // may complete in the background, but is read on the next loop.
      const bool wasStreaming = streaming;
      streaming = false;
      scanBus(pressureBus, "A2");
      scanBus(tofBus, "B2");
      streaming = wasStreaming;
    }
    else if (c == 'p' || c == 'P') {
      streaming = !streaming;
      Serial.println(streaming ? "# STREAM_RUNNING" : "# STREAM_PAUSED");
    } else if (c == 'h' || c == 'H') {
      Serial.println("# Commands: s=status; i=I2C scan; p=pause/resume; h=help");
    }
  }
  if (streaming) {
    // Both buses can be serviced independently; pressure conversion is non-blocking.
    servicePressure(millis());
    serviceTof(millis());
  }
  delay(5);
}
