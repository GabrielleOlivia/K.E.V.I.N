// K.E.V.I.N. SAMD21 Sensor A1 live VL6180X distance measurements.
// Pressure module and BOTH IMUs must be disconnected for this isolated test.
// The BHI360 chest IMU shares VL6180X's 0x29 address on Sensor A.
// Adapted from the existing STM32 VL6180X bench code; raw ranging only.
// Not calibrated compression depth and not for clinical monitoring.
#include <Arduino.h>
#include <Wire.h>
#include "wiring_private.h"
#include "vl6180x.h"

namespace {
constexpr uint8_t kSda = 11; // old SAMD21 Sensor A1: PA16, SERCOM1
constexpr uint8_t kScl = 13; // old SAMD21 Sensor A1: PA17, SERCOM1
constexpr uint32_t kSampleMs = 250; // 4 samples/second
constexpr uint32_t kRetryMs = 2000;
constexpr uint32_t kMeasurementTimeoutMs = 100;

TwoWire sensorA(&sercom1, kSda, kScl);
vl6180x::Device tof(sensorA);
bool ready = false;
bool streaming = true;
uint32_t lastSampleMs = 0, lastIdentifyMs = 0;

bool pinIs(uint8_t index, uint32_t port, uint32_t pin) {
  return static_cast<uint32_t>(g_APinDescription[index].ulPort) == port &&
         g_APinDescription[index].ulPin == pin;
}

void identifyAndInitialize() {
  lastIdentifyMs = millis();
  ready = false;
  if (!tof.present()) {
    Serial.println("# TOF_ABSENT I2C address 0x29");
    return;
  }

  vl6180x::Identity identity;
  if (!tof.readIdentity(identity)) {
    Serial.println("# TOF_ID_READ_FAILED");
    return;
  }
  Serial.print("# TOF_MODEL_ID value=0x");
  if (identity.modelId < 16) Serial.print('0');
  Serial.print(identity.modelId, HEX);
  Serial.print(" expected=0xB4 identified=");
  Serial.println(identity.modelId == vl6180x::EXPECTED_MODEL_ID ? 1 : 0);

  if (identity.modelId != vl6180x::EXPECTED_MODEL_ID) {
    Serial.println("# TOF_WRONG_DEVICE: do not initialize unknown device");
    return;
  }

  // Required VL6180X setup writes, matching the STM32's verified driver.
  // Only initialized AFTER exact VL6180X model-ID validation succeeds.
  if (!tof.init()) {
    Serial.println("# TOF_INIT_FAILED: check power and I2C wiring");
    return;
  }

  ready = true;
  lastSampleMs = millis();
  Serial.println("# TOF_READY: streaming raw distances in mm at ~4 Hz");
  Serial.println("# Each valid=1 sample has err=0; invalid samples must be ignored");
}

void sampleIfDue() {
  if (!streaming) return;
  uint32_t now = millis();
  if (!ready) {
    if (now - lastIdentifyMs >= kRetryMs) identifyAndInitialize();
    return;
  }
  if (now - lastSampleMs < kSampleMs) return;
  lastSampleMs = now;

  vl6180x::Range range;
  if (!tof.measure(range, kMeasurementTimeoutMs)) {
    Serial.println("# TOF_READ_FAILED: timeout or I2C error; retry in 2 s");
    ready = false;
    lastIdentifyMs = millis();
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

void SERCOM1_Handler() { sensorA.onService(); }

void setup() {
  Serial.begin(115200);
  const uint32_t started = millis();
  while (!Serial && (millis() - started < 4000)) delay(10);

  Serial.println("# KEVIN SAMD21 VL6180X SENSOR A1 LIVE RANGING v0.2");
  Serial.println("# Isolated ToF only: pressure + both IMUs disconnected");
  Serial.println("# Raw mm are only valid when err=0 and valid=1");
  if (!pinIs(kSda, PORTA, 16) || !pinIs(kScl, PORTA, 17)) {
    Serial.println("# FATAL PINMAP_MISMATCH: no bus initialized");
    while (true) delay(1000);
  }

  sensorA.begin();
  pinPeripheral(kSda, PIO_SERCOM);
  pinPeripheral(kScl, PIO_SERCOM);
  sensorA.setClock(100000);
  delay(200);
  identifyAndInitialize();
  Serial.println("# Commands: s=retry identify; p=pause/resume stream; h=help");
}

void loop() {
  while (Serial.available()) {
    char command = static_cast<char>(Serial.read());
    if (command == 's' || command == 'S') identifyAndInitialize();
    else if (command == 'p' || command == 'P') {
      streaming = !streaming;
      Serial.println(streaming ? "# STREAM_RUNNING" : "# STREAM_PAUSED");
      if (streaming) lastSampleMs = millis();
    } else if (command == 'h' || command == 'H') {
      Serial.println("# s=retry ToF initialization; p=pause/resume readings; h=help");
    }
  }
  sampleIfDue();
  delay(5);
}
