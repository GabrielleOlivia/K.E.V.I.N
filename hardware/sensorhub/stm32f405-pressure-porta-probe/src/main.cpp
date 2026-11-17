// K.E.V.I.N. STM32F405 pressure-only Port A upper diagnostic (v0.1)
// Reuses MCP3426 0x68, configuration 0x88 from proven SAMD21 pressure prototype.
// *** TEST ONE SENSOR AT A TIME ***
// Remove VL6180X from the proven four-pin Port A upper connector with USB OFF.
// Only connect the SimModule Pressure v2.0 board using an electrically VERIFIED,
// matching four-pin keyed cable. Do NOT use the unverified Port B five-wire harness.
// The physical carrier is v1.0.3; v1.1.0b Port B assumptions do NOT apply.
//
// Hardware control touches ONLY the already-proven Port A upper rail PC9,
// I2C1 SDA PB7 / SCL PB6. No Port B/I2C2 pins are touched.
// Bench manikin research only; counts are not calibrated airway pressure.

#include <Arduino.h>
#include <Wire.h>

#ifndef KEVIN_PRESSURE_PORTA_ELECTRICAL_VERIFIED
#define KEVIN_PRESSURE_PORTA_ELECTRICAL_VERIFIED 0
#endif

// MPXV5010GP datasheet calls for 4.75-5.25V sensor supply. Port A upper
// switched rail was only observed to power a 3.3V ToF breakout. This
// diagnostic is locked until the module's actual 5V supply and its separate
// 3.3V MCP3426 I2C interface are electrically verified. Firmware cannot
// provide the missing 5V supply through the ToF rail.

namespace {
constexpr uint32_t kPortAUpperRail = PC9;
constexpr uint8_t kMcp3426Address = 0x68;
constexpr uint8_t kMcp3426Config = 0x88;  // CH1, 16-bit, one-shot, PGA x1
constexpr uint32_t kConversionTimeMs = 95; // 15 SPS nominal, margin
constexpr uint32_t kSamplePeriodMs = 250;
constexpr uint32_t kProbePeriodMs = 2000;
TwoWire pressureBus(PB7, PB6);            // verified ToF physical Port A upper bus

bool adcAcknowledged = false;
bool conversionPending = false;
uint32_t conversionStarted = 0;
uint32_t lastConversionStart = 0;
uint32_t lastProbe = 0;
uint32_t validSamples = 0;
uint32_t invalidSamples = 0;

bool ping() {
  pressureBus.beginTransmission(kMcp3426Address);
  return pressureBus.endTransmission() == 0;
}

void probe() {
  adcAcknowledged = ping();
  lastProbe = millis();
  Serial.print("# ADC_PROBE bus=I2C1 port=A_upper address=0x68 ack=");
  Serial.println(adcAcknowledged ? 1 : 0);
  if (!adcAcknowledged) Serial.println("# ADC_ABSENT: recheck keyed cable and module electronics with power OFF");
}

void startConversion() {
  pressureBus.beginTransmission(kMcp3426Address);
  pressureBus.write(kMcp3426Config);
  const uint8_t rc = pressureBus.endTransmission();
  if (rc) {
    ++invalidSamples;
    adcAcknowledged = false;
    Serial.print("# ADC_FAULT config_write_error=");
    Serial.println(rc);
    return;
  }
  conversionPending = true;
  conversionStarted = millis();
  lastConversionStart = conversionStarted;
}

void finishConversion() {
  conversionPending = false;
  const uint8_t count =
      pressureBus.requestFrom(kMcp3426Address, static_cast<uint8_t>(3));
  if (count != 3) {
    while (pressureBus.available()) pressureBus.read();
    ++invalidSamples;
    Serial.print("# ADC_FAULT short_read bytes=");
    Serial.println(count);
    return;
  }
  const uint8_t hi = pressureBus.read();
  const uint8_t lo = pressureBus.read();
  const uint8_t config = pressureBus.read();
  if (config & 0x80) {
    ++invalidSamples;
    Serial.println("# ADC_FAULT conversion_not_ready");
    return;
  }
  if ((config & 0x7F) != (kMcp3426Config & 0x7F)) {
    ++invalidSamples;
    Serial.print("# ADC_FAULT config_mismatch=0x");
    Serial.println(config, HEX);
    return;
  }
  const int16_t raw =
      static_cast<int16_t>((static_cast<uint16_t>(hi) << 8) | lo);
  ++validSamples;
  Serial.print("# pressure,t_ms=");
  Serial.print(millis());
  Serial.print(",raw_adc=");
  Serial.print(raw);
  Serial.print(",valid=1,total_valid=");
  Serial.print(validSamples);
  Serial.print(",total_invalid=");
  Serial.println(invalidSamples);
}
} // namespace

void setup() {
  Serial.begin(115200);
  const uint32_t t0 = millis();
  while (!Serial && millis() - t0 < 3000) delay(10);
  Serial.println("# KEVIN STM32 PRESSURE-ONLY Port A upper v0.1");
  Serial.println("# Expected: MCP3426 ADC at 0x68; MPXV5010GP module");
  Serial.println("# Sensor supply: proven ToF-switched Port A upper rail PC9");
  Serial.println("# Port B disabled; ToF intentionally disconnected");
  Serial.println("# NO CALIBRATION: raw ADC counts only");
  if (!KEVIN_PRESSURE_PORTA_ELECTRICAL_VERIFIED) {
    Serial.println("# SAFETY_LOCK pressure module 5V supply and 4-pin I2C wiring unverified");
    Serial.println("# Port A power and I2C kept OFF; no sensor probe performed");
    return;
  }
  // ONLY enable after actual voltage and cable pinout are verified.
  digitalWrite(kPortAUpperRail, LOW);
  pinMode(kPortAUpperRail, OUTPUT);
  digitalWrite(kPortAUpperRail, HIGH);
  delay(80);
  pressureBus.begin();
  pressureBus.setClock(100000);
  probe();
  Serial.println("# Commands: s=status, h=help");
}

void loop() {
  if (!KEVIN_PRESSURE_PORTA_ELECTRICAL_VERIFIED) {
    static uint32_t heartbeat = 0;
    if (millis() - heartbeat >= 2000) {
      Serial.println("# SAFETY_LOCK_HEARTBEAT pressure I2C and rail disabled");
      heartbeat = millis();
    }
    delay(20);
    return;
  }
  while (Serial.available()) {
    const char c = static_cast<char>(Serial.read());
    if (c == 's' || c == 'S') probe();
    if (c == 'h' || c == 'H')
      Serial.println("# s=read I2C ACK; pressure raw counts will stream if found");
  }
  const uint32_t now = millis();
  if (!adcAcknowledged) {
    if (now - lastProbe >= kProbePeriodMs) probe();
    delay(20);
    return;
  }
  if (!conversionPending) {
    if (now - lastConversionStart >= kSamplePeriodMs) startConversion();
  } else if (now - conversionStarted >= kConversionTimeMs) {
    finishConversion();
  }
  delay(5);
}
