// K.E.V.I.N.: independent I2C buses, SAMD21 Sensor A2 pressure + Sensor B2 VL6180X.
// Bench diagnostics only: ADC counts are NOT calibrated pressure; mm are raw ToF distances.
// Wiring changes only with USB disconnected. Pressure MCP3426 0x68 on SERCOM1,
// VL6180X 0x29 on SERCOM2. No IMUs connected.
#include <Arduino.h>
#include <Wire.h>
#include "wiring_private.h"
#include "vl6180x.h"
#include "bench_command.h"

namespace {
constexpr uint8_t kPressureSda = 11; // Feather M0 index for PA16, SERCOM1
constexpr uint8_t kPressureScl = 13; // Feather M0 index for PA17, SERCOM1
constexpr uint8_t kTofSda = 28;     // Feather M0 index for PA12, SERCOM2
constexpr uint8_t kTofScl = 39;     // Feather M0 index for PA13, SERCOM2
constexpr uint8_t kPressureAddr = 0x68;
// Optional single BHI360 IMU on PHYSICAL A1, sharing Sensor A SERCOM1 with pressure.
// ToF remains on PHYSICAL B1 (SERCOM2), despite this historical firmware's B2 labels.
// 0x29 on Sensor A and 0x29 on Sensor B do NOT conflict: they are separate buses.
constexpr uint8_t kImuA1Addr = 0x29;
constexpr uint8_t kBhiFuserIdReg = 0x1C;
constexpr uint8_t kBhiChipIdReg = 0x2B;
constexpr uint8_t kBhiRevisionReg = 0x1D;
constexpr uint8_t kBhiBootStatusReg = 0x25;
constexpr uint8_t kBhiErrorReg = 0x2E;
constexpr uint8_t kExpectedFuserId = 0x89;
constexpr uint8_t kExpectedChipId = 0x7A;
constexpr uint8_t kPressureConfig = 0x88; // MCP3426 CH1 one-shot, 16bit, gain 1
constexpr uint32_t kPressurePeriodMs = 250;
constexpr uint32_t kPressureWaitMs = 110;
constexpr uint32_t kPressurePollMs = 10;
constexpr uint32_t kPressureDeadlineMs = 200;
constexpr uint32_t kTofPeriodMs = 250;
constexpr uint32_t kTofTimeoutMs = 100;
constexpr uint32_t kRetryMs = 2000;

TwoWire pressureBus(&sercom1, kPressureSda, kPressureScl);
TwoWire tofBus(&sercom2, kTofSda, kTofScl);
vl6180x::Device tof(tofBus);

bool pressurePresent = false;
bool pressurePending = false;
bool tofReady = false;
bool usePressure = false;
bool useTof = false;
bool acquisitionStarted = false;
bool streaming = false;
uint32_t lastPressureReadMs = 0;
uint32_t pressureStartedMs = 0, lastPressureStartMs = 0, lastPressureProbeMs = 0;
uint32_t lastTofMs = 0, lastTofProbeMs = 0;

bool pinIs(uint8_t index, uint32_t port, uint32_t pin) {
  return index < PINS_COUNT &&
         static_cast<uint32_t>(g_APinDescription[index].ulPort) == port &&
         g_APinDescription[index].ulPin == pin;
}

uint8_t wireStatus(TwoWire &bus, uint8_t address) {
  bus.beginTransmission(address);
  return bus.endTransmission(true);
}

// Read only BHI360 register values. Writing a register *index* is required by
// its I2C read protocol; this does NOT reset, configure, or upload firmware.
bool readBhiRegA1(uint8_t reg, uint8_t &value) {
  pressureBus.beginTransmission(kImuA1Addr);
  const bool registerSent = pressureBus.write(reg) == 1;
  const uint8_t txStatus = pressureBus.endTransmission(false);
  if (!registerSent || txStatus != 0) return false;
  const uint8_t received = pressureBus.requestFrom(
      kImuA1Addr, static_cast<uint8_t>(1), static_cast<uint8_t>(true));
  if (received != 1 || !pressureBus.available()) {
    while (pressureBus.available()) pressureBus.read();
    return false;
  }
  value = static_cast<uint8_t>(pressureBus.read());
  return true;
}

// Explicit, operator-triggered discovery only (command m); no BHI firmware
// boot/download until the separate historical IMU startup issue is resolved.
// Do not assume ANY motion/quaternion data merely because these IDs match.
void probeImuA1() {
  if (!usePressure) {
    Serial.println("# IMU_A1_BUS_A_NOT_SELECTED choose a or c after a cold reset");
    return;
  }
  const uint8_t ack = wireStatus(pressureBus, kImuA1Addr);
  Serial.print("# IMU_A1_ACK bus=A1_shared_A2 address=0x29 wire_status=");
  Serial.print(ack);
  Serial.print(" ack=");
  Serial.println(ack == 0 ? 1 : 0);
  if (ack != 0) return;

  uint8_t fuser = 0, chip = 0;
  if (!readBhiRegA1(kBhiFuserIdReg, fuser) ||
      !readBhiRegA1(kBhiChipIdReg, chip)) {
    Serial.println("# IMU_A1_ID_READ_FAILED motion=UNAVAILABLE");
    return;
  }
  const bool valid = fuser == kExpectedFuserId && chip == kExpectedChipId;
  Serial.print("# IMU_A1_ID fuser=0x");
  Serial.print(fuser, HEX);
  Serial.print(" chip=0x");
  Serial.print(chip, HEX);
  Serial.print(" identified=");
  Serial.print(valid ? 1 : 0);
  Serial.println(" motion=UNAVAILABLE");
  if (!valid) {
    Serial.println("# IMU_A1_UNKNOWN_RESPONDER no further register reads");
    return;
  }

  uint8_t revision = 0, boot = 0, error = 0;
  if (readBhiRegA1(kBhiRevisionReg, revision) &&
      readBhiRegA1(kBhiBootStatusReg, boot) &&
      readBhiRegA1(kBhiErrorReg, error)) {
    Serial.print("# IMU_A1_HEALTH revision=0x");
    Serial.print(revision, HEX);
    Serial.print(" boot=0x");
    Serial.print(boot, HEX);
    Serial.print(" error=0x");
    Serial.println(error, HEX);
  } else {
    Serial.println("# IMU_A1_HEALTH_READ_FAILED");
  }
  Serial.println("# IMU_A1_NO_FIRMWARE_UPLOAD orientation=UNAVAILABLE");
}

void scanBus(TwoWire &bus, const char *name) {
  Serial.print("# SCAN_START bus=");
  Serial.println(name);
  uint8_t found = 0;
  for (uint8_t addr = 0x08; addr <= 0x77; ++addr) {
    if (wireStatus(bus, addr) == 0) {
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
void printAck(int code) {
  if (code < 0) Serial.print("off");
  else Serial.print(code == 0 ? 1 : 0);
}

void status() {
  const int a = usePressure ? wireStatus(pressureBus, kPressureAddr) : -1;
  const int b = useTof ? wireStatus(tofBus, vl6180x::ADDRESS) : -1;
  Serial.print("# STATUS pressure_A2_ack=");
  printAck(a);
  Serial.print(" tof_B2_ack=");
  printAck(b);
  Serial.print(" tof_initialized=");
  Serial.print(tofReady && b == 0 ? 1 : 0);
  Serial.print(" pressure_wire=");
  Serial.print(a);
  Serial.print(" tof_wire=");
  Serial.println(b);
}

void pressureFault(const char *reason, uint8_t code) {
  pressurePending = false;
  pressurePresent = false;
  lastPressureProbeMs = millis();
  Serial.print("# PRESSURE_FAULT reason=");
  Serial.print(reason);
  Serial.print(" wire_status=");
  Serial.println(code);
}

// Emits 1 raw ADC row after MCP3426 conversion has completed.
// Invalid, stale and partial reads are never silently interpreted as zero.
void servicePressure(uint32_t now) {
  if (!pressurePresent) {
    if (now - lastPressureProbeMs >= kRetryMs) {
      lastPressureProbeMs = now;
      pressurePresent = wireStatus(pressureBus, kPressureAddr) == 0;
      if (pressurePresent) Serial.println("# PRESSURE_RECONNECTED A2 0x68");
      else Serial.println("# PRESSURE_ABSENT A2 0x68");
    }
    return;
  }
  if (pressurePending) {
    if (now - pressureStartedMs < kPressureWaitMs ||
        now - lastPressureReadMs < kPressurePollMs) return;
    lastPressureReadMs = now;
    const uint8_t count = pressureBus.requestFrom(kPressureAddr, static_cast<uint8_t>(3));
    if (count != 3) {
      while (pressureBus.available()) pressureBus.read();
      pressurePending = false;
      Serial.print("# PRESSURE_SAMPLE_INVALID reason=short_read rx_count=");
      Serial.println(count);
      // A failed read can be transient; reconfirm address before retry.
      const uint8_t code = wireStatus(pressureBus, kPressureAddr);
      if (code != 0) pressureFault("address_phase", code);
      return;
    }
    const uint8_t hi = pressureBus.read();
    const uint8_t lo = pressureBus.read();
    const uint8_t config = pressureBus.read();
    if ((config & 0x7F) != (kPressureConfig & 0x7F)) {
      pressurePending = false;
      Serial.print("# PRESSURE_SAMPLE_INVALID reason=config_mismatch config=0x");
      Serial.println(config, HEX);
      return;
    }
    if ((config & 0x80) != 0) {
      if (now - pressureStartedMs >= kPressureDeadlineMs) {
        pressurePending = false;
        Serial.println("# PRESSURE_SAMPLE_INVALID reason=adc_busy_timeout");
      }
      return;
    }
    pressurePending = false;
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
  const uint8_t code = pressureBus.endTransmission(true);
  if (code != 0) {
    pressureFault("config_write", code);
    return;
  }
  pressureStartedMs = millis();
  lastPressureReadMs = pressureStartedMs;
  pressurePending = true;
}

void identifyTof() {
  lastTofProbeMs = millis();
  tofReady = false;
  if (!tof.present()) {
    Serial.println("# TOF_ABSENT B2 0x29");
    return;
  }
  uint8_t modelId = 0;
  if (!tof.read8(vl6180x::IDENTIFICATION__MODEL_ID, modelId)) {
    Serial.println("# TOF_ID_READ_FAILED B2");
    return;
  }
  Serial.print("# TOF_MODEL_ID value=0x");
  if (modelId < 16) Serial.print('0');
  Serial.print(modelId, HEX);
  Serial.print(" expected=0xB4 identified=");
  Serial.println(modelId == vl6180x::EXPECTED_MODEL_ID ? 1 : 0);

  if (modelId != vl6180x::EXPECTED_MODEL_ID) {
    Serial.println("# STOP TOF_WRONG_DEVICE power off and identify the B2 module");
    while (true) delay(1000);
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
  Serial.println(range.errorCode == 0 && range.mm != 0xFF ? 1 : 0);
}
void help() {
  Serial.println("# KEVIN SAMD21 A2-pressure B1-ToF A1-BHI360-probe v2 (UNTESTED)");
  Serial.println("# a=A2 only, b=B2 only, c=both; select once per cold setup");
  Serial.println("# s=target ACK/status, i=address scan, m=read-only BHI360 A1 ID");
  Serial.println("# g=pressure/ToF acquisition, p=pause/resume, h=help; IMU orientation NOT ENABLED");
  Serial.println("# Logical label B2 refers to the B bus; physical ToF was tested on B1");
}

bool linesReleased(uint8_t sda, uint8_t scl, const char *name) {
  pinMode(sda, INPUT);
  pinMode(scl, INPUT);
  delay(1);
  if (digitalRead(sda) && digitalRead(scl)) return true;
  Serial.print("# STOP idle_line_low bus=");
  Serial.println(name);
  return false;
}

bool muxIsC(uint8_t index) {
  const auto &desc = g_APinDescription[index];
  const auto &port = PORT->Group[desc.ulPort];
  const uint8_t pin = desc.ulPin;
  const uint8_t shift = (pin & 1) ? 4 : 0;
  return port.PINCFG[pin].bit.PMUXEN &&
         ((port.PMUX[pin / 2].reg >> shift) & 0x0F) == PIO_SERCOM;
}

bool startBus(TwoWire &bus, uint8_t sda, uint8_t scl) {
  bus.begin();
  // begin() selects each Feather pin's default peripheral. Override it afterwards.
  if (pinPeripheral(sda, PIO_SERCOM) != 0 || pinPeripheral(scl, PIO_SERCOM) != 0)
    return false;
  bus.setClock(100000);
  return muxIsC(sda) && muxIsC(scl);
}

void selectStage(char c) {
  if (usePressure || useTof) {
    Serial.println("# Stage already selected. Power off before changing the wiring.");
    return;
  }
  usePressure = c == 'a' || c == 'c';
  useTof = c == 'b' || c == 'c';
  if ((usePressure && !linesReleased(kPressureSda, kPressureScl, "A2")) ||
      (useTof && !linesReleased(kTofSda, kTofScl, "B2"))) {
    while (true) delay(1000);
  }
  if ((usePressure && !startBus(pressureBus, kPressureSda, kPressureScl)) ||
      (useTof && !startBus(tofBus, kTofSda, kTofScl))) {
    Serial.println("# STOP PINMUX_MISMATCH");
    while (true) delay(1000);
  }
  delay(200);
  status();  // address-only until the operator sends g
}

void startAcquisition() {
  if (acquisitionStarted) return;
  acquisitionStarted = true;
  streaming = true;
  if (usePressure) {
    pressurePresent = wireStatus(pressureBus, kPressureAddr) == 0;
    lastPressureProbeMs = millis();
    Serial.println(pressurePresent ? "# PRESSURE_PRESENT A2 0x68" :
                                     "# PRESSURE_ABSENT A2 0x68");
  }
  if (useTof) identifyTof();
}
} // namespace

void SERCOM1_Handler() { pressureBus.onService(); }
void SERCOM2_Handler() { tofBus.onService(); }

void setup() {
  Serial.begin(115200);
  const uint32_t started = millis();
  while (!Serial && millis() - started < 4000) delay(10);
  help();
  if (!pinIs(kPressureSda, PORTA, 16) || !pinIs(kPressureScl, PORTA, 17) ||
      !pinIs(kTofSda, PORTA, 12) || !pinIs(kTofScl, PORTA, 13)) {
    Serial.println("# STOP PINMAP_MISMATCH");
    while (true) delay(1000);
  }
}

void loop() {
  const char c = readBenchCommand();
  if (c == 'a' || c == 'b' || c == 'c') selectStage(c);
  else if (c == 'h' || c == '?') help();
  else if (c && !usePressure && !useTof) Serial.println("# Select a, b or c first");
  else if (c == 's') status();
  else if (c == 'm') probeImuA1();
  else if (c == 'i') {
    if (usePressure) scanBus(pressureBus, "A2");
    if (useTof) scanBus(tofBus, "B2");
  } else if (c == 'g') startAcquisition();
  else if (c == 'p' && acquisitionStarted) {
    streaming = !streaming;
    pressurePending = false;  // discard any conversion from before the pause
    Serial.println(streaming ? "# STREAM_RUNNING" : "# STREAM_PAUSED");
  }
  if (streaming && usePressure) servicePressure(millis());
  if (streaming && useTof) serviceTof(millis());
  delay(5);
}
