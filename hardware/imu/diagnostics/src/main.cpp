// K.E.V.I.N. RobotPatient BHI360 identification / I2C diagnostic.
// Does NOT upload BHI360 firmware or generate orientation data.
// Do not connect unknown-voltage breakouts until the connector is verified.
// No I2C writes except the address/register selection required for reads.
// Pressure acquisition firmware is a separate project and is NOT modified here.

#include <Arduino.h>
#include <Wire.h>
#include "wiring_private.h"

namespace {
constexpr uint8_t PIN_A_SDA = 11; // PA16 in Feather M0 Express variant (verified for pressure Sensor A2)
constexpr uint8_t PIN_A_SCL = 13; // PA17
constexpr uint8_t PIN_B_SDA = 28; // PA12 in Feather M0 Express variant (proposed Sensor B bus)
constexpr uint8_t PIN_B_SCL = 39; // PA13 in Feather M0 Express variant (proposed Sensor B bus)
constexpr uint8_t BHI_ADDR_LOW = 0x28;
constexpr uint8_t BHI_ADDR_HIGH = 0x29;
constexpr uint8_t PRESSURE_ADC_ADDR = 0x68;
constexpr uint8_t BHI_ID_REG = 0x1C;
constexpr uint8_t BHI_REV_REG = 0x1D;
constexpr uint8_t BHI_BOOT_REG = 0x25;
constexpr uint8_t BHI_EXPECTED_ID = 0x89;
constexpr uint32_t PROBE_INTERVAL_MS = 5000;

TwoWire wireA(&sercom1, PIN_A_SDA, PIN_A_SCL);
TwoWire wireB(&sercom2, PIN_B_SDA, PIN_B_SCL);
uint32_t lastProbe = 0;

bool pinMatches(uint8_t index, uint32_t port, uint32_t pin) {
  return g_APinDescription[index].ulPort == port && g_APinDescription[index].ulPin == pin;
}

bool addressAck(TwoWire &bus, uint8_t address) {
  bus.beginTransmission(address);
  return bus.endTransmission(true) == 0;
}

// Non-destructive BHI360 register access; register pointer write + repeated start.
// No firmware upload, resets, or configuration writes are performed.
bool readRegister(TwoWire &bus, uint8_t address, uint8_t reg, uint8_t &value) {
  bus.beginTransmission(address);
  bus.write(reg);
  if (bus.endTransmission(false) != 0) {
    return false;
  }
  if (bus.requestFrom(address, static_cast<uint8_t>(1), static_cast<uint8_t>(true)) != 1) {
    while (bus.available()) bus.read();
    return false;
  }
  if (!bus.available()) return false;
  value = static_cast<uint8_t>(bus.read());
  return true;
}

void printHex(uint8_t number) {
  Serial.print("0x");
  if (number < 0x10) Serial.print('0');
  Serial.print(number, HEX);
}

void inspectBhi(TwoWire &bus, const char *busName, uint8_t address) {
  Serial.print("# "); Serial.print(busName); Serial.print(" BHI candidate ");
  printHex(address);
  if (!addressAck(bus, address)) {
    Serial.println(" NO_ACK");
    return;
  }
  Serial.print(" ACK");
  uint8_t id = 0;
  if (!readRegister(bus, address, BHI_ID_REG, id)) {
    Serial.println(" ID_READ_FAILED (address response does not prove BHI360)");
    return;
  }
  Serial.print(" FUSER2_ID="); printHex(id);
  if (id != BHI_EXPECTED_ID) {
    Serial.println(" NOT_BHI360_ID (do not initialize as BHI360)");
    return;
  }
  Serial.print(" BHI360_IDENTIFIED");
  uint8_t revision = 0;
  if (readRegister(bus, address, BHI_REV_REG, revision)) {
    Serial.print(" REV="); printHex(revision);
  } else {
    Serial.print(" REV_READ_FAILED");
  }
  uint8_t boot = 0;
  if (readRegister(bus, address, BHI_BOOT_REG, boot)) {
    Serial.print(" BOOT_STATUS="); printHex(boot);
  } else {
    Serial.print(" BOOT_STATUS_READ_FAILED");
  }
  Serial.println(" (identification only; fusion not enabled)");
}

void probeKnownDevices() {
  Serial.print("# PROBE_BEGIN t_ms="); Serial.println(millis());
  Serial.print("# Bus A pressure ADC "); printHex(PRESSURE_ADC_ADDR);
  Serial.println(addressAck(wireA, PRESSURE_ADC_ADDR) ? " ACK (not a pressure measurement)" : " NO_ACK");
  inspectBhi(wireA, "A", BHI_ADDR_LOW);
  inspectBhi(wireA, "A", BHI_ADDR_HIGH);
  inspectBhi(wireB, "B", BHI_ADDR_LOW);
  inspectBhi(wireB, "B", BHI_ADDR_HIGH);
  Serial.println("# PROBE_END");
}

void scanBus(TwoWire &bus, const char *name) {
  Serial.print("# SCAN_BEGIN "); Serial.println(name);
  uint8_t found = 0;
  for (uint8_t address = 0x08; address <= 0x77; ++address) {
    if (addressAck(bus, address)) {
      Serial.print("# "); Serial.print(name); Serial.print(" ACK "); printHex(address);
      Serial.println();
      ++found;
    }
  }
  Serial.print("# SCAN_END "); Serial.print(name);
  Serial.print(" count="); Serial.println(found);
}

void printHelp() {
  Serial.println("# Commands: p = probe known addresses; s = scan both buses; h = help");
  Serial.println("# Diagnostic only: no patient state, no quaternion output, no firmware uploads.");
}
} // namespace

// The SensorHub uses SERCOM1 on A and is expected to use SERCOM2 on B.
void SERCOM1_Handler() { wireA.onService(); }
void SERCOM2_Handler() { wireB.onService(); }

void setup() {
  Serial.begin(115200);
  uint32_t start = millis();
  while (!Serial && millis() - start < 3500) { delay(10); }
  Serial.println("# KEVIN_BHI360_ID_PROBE v0.1");
  Serial.println("# Standalone firmware - does not sample pressure or initialize BHI360 fusion.");
  if (!pinMatches(PIN_A_SDA, PORTA, 16) || !pinMatches(PIN_A_SCL, PORTA, 17) ||
      !pinMatches(PIN_B_SDA, PORTA, 12) || !pinMatches(PIN_B_SCL, PORTA, 13)) {
    Serial.println("# FATAL PINMAP_MISMATCH: wrong board variant; I2C disabled.");
    while (true) { delay(1000); }
  }
  Serial.println("# PINMAP_OK A=PA16/PA17 (SERCOM1), B=PA12/PA13 (SERCOM2)");
  wireA.begin();
  pinPeripheral(PIN_A_SDA, PIO_SERCOM);
  pinPeripheral(PIN_A_SCL, PIO_SERCOM);
  wireA.setClock(100000);
  wireB.begin();
  pinPeripheral(PIN_B_SDA, PIO_SERCOM);
  pinPeripheral(PIN_B_SCL, PIO_SERCOM);
  wireB.setClock(100000);
  printHelp();
  probeKnownDevices();
  lastProbe = millis();
}

void loop() {
  while (Serial.available()) {
    char c = static_cast<char>(Serial.read());
    if (c == 'p' || c == 'P') { probeKnownDevices(); lastProbe = millis(); }
    if (c == 's' || c == 'S') { scanBus(wireA, "A"); scanBus(wireB, "B"); }
    if (c == 'h' || c == 'H') printHelp();
  }
  if (static_cast<uint32_t>(millis() - lastProbe) >= PROBE_INTERVAL_MS) {
    probeKnownDevices();
    lastProbe = millis();
  }
  delay(20);
}
