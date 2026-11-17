// K.E.V.I.N. SAMD21 VL6180X read-only I2C identity test.
// Port A1 (same Sensor A bus as pressure A2). Unplug pressure + both IMUs.
// Address 0x29 is shared with BHI360, so do not connect that IMU on bus A.
// No chip reset or configuration writes; no distance sampling yet.
// Manikin bench diagnostic only, not a medical measurement.
#include <Arduino.h>
#include <Wire.h>
#include "wiring_private.h"

constexpr uint8_t kSda = 11; // PA16, SERCOM1: old SensorHub A
constexpr uint8_t kScl = 13; // PA17, SERCOM1: old SensorHub A
constexpr uint8_t kTofAddr = 0x29;
constexpr uint16_t kModelIdReg = 0x0000; // VL6180X IDENTIFICATION_MODEL_ID
constexpr uint8_t kExpectedModelId = 0xB4;

TwoWire sensorA(&sercom1, kSda, kScl);
void SERCOM1_Handler() { sensorA.onService(); }

bool pinIs(uint8_t index, uint32_t port, uint32_t pin) {
  return static_cast<uint32_t>(g_APinDescription[index].ulPort) == port &&
         g_APinDescription[index].ulPin == pin;
}
bool ack(uint8_t address) {
  sensorA.beginTransmission(address);
  return sensorA.endTransmission(true) == 0;
}
bool readRegister8(uint16_t reg, uint8_t &value) {
  sensorA.beginTransmission(kTofAddr);
  sensorA.write(static_cast<uint8_t>(reg >> 8));
  sensorA.write(static_cast<uint8_t>(reg & 0xFF));
  const uint8_t result = sensorA.endTransmission(false); // repeated start
  if (result != 0) return false;
  if (sensorA.requestFrom(kTofAddr, static_cast<uint8_t>(1),
                          static_cast<uint8_t>(true)) != 1) {
    while (sensorA.available()) sensorA.read();
    return false;
  }
  if (!sensorA.available()) return false;
  value = static_cast<uint8_t>(sensorA.read());
  return true;
}
void report() {
  const bool present = ack(kTofAddr);
  Serial.print("# TOF_A1 address=0x29 ack=");
  Serial.println(present ? 1 : 0);
  if (!present) {
    Serial.println("# TOF_NOT_DETECTED check power, cable pins, and 0x29 conflict");
    return;
  }
  uint8_t modelId = 0;
  if (!readRegister8(kModelIdReg, modelId)) {
    Serial.println("# TOF_ID_READ_FAILED (ACK alone does not prove VL6180X)");
    return;
  }
  Serial.print("# TOF_MODEL_ID value=0x");
  if (modelId < 16) Serial.print('0');
  Serial.print(modelId, HEX);
  Serial.print(" expected=0xB4 identified=");
  Serial.println(modelId == kExpectedModelId ? 1 : 0);
}
void setup() {
  Serial.begin(115200);
  const unsigned long t0 = millis();
  while (!Serial && millis() - t0 < 4000) delay(10);
  Serial.println("# KEVIN SAMD21 TOF VL6180X A1 READ-ONLY ID v0.1");
  Serial.println("# No pressure or IMUs connected; only address 0x29 probed");
  if (!pinIs(kSda, PORTA, 16) || !pinIs(kScl, PORTA, 17)) {
    Serial.println("# FATAL PINMAP_MISMATCH: I2C not initialized");
    while (true) delay(1000);
  }
  sensorA.begin();
  pinPeripheral(kSda, PIO_SERCOM);
  pinPeripheral(kScl, PIO_SERCOM);
  sensorA.setClock(100000);
  delay(200);
  report();
  Serial.println("# Commands: s=retry ToF ACK and model ID; h=help");
}
void loop() {
  while (Serial.available()) {
    const char c = static_cast<char>(Serial.read());
    if (c == 's' || c == 'S') report();
    if (c == 'h' || c == 'H') Serial.println("# s=read-only VL6180X address and ID check");
  }
  delay(20);
}
