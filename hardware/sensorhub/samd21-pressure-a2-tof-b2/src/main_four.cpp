// K.E.V.I.N. FOUR-SENSOR BENCH EXPERIMENT v0.3
// Physical A1: BHI360 0x29 + BMM350 0x15 (head) on SERCOM1
// Physical A2: MCP3426 0x68 (pressure) on SERCOM1
// Physical B1: VL6180X 0x29 (ToF) on SERCOM2
// Physical B2: BHI360 0x28 + BMM350 0x14 (chest) on SERCOM2
// Sensor A and B are independent I2C buses; B1 and B2 SHARE Bus B.
// Two IMUs output RAW XYZ accelerometer samples; desktop estimates relative tilt.
// The user must repair loose wiring BEFORE connecting all four modules.
// Training-only uncalibrated, not suitable for diagnosing airway obstruction.
#include <Arduino.h>
#include <Wire.h>
#include "wiring_private.h"
#include "vl6180x.h"
#include "bench_command.h"
#include "bhi360.h"
#include "bhi360_event_data.h"
#include "bhi360_virtual_sensor_conf_param.h"
#include "bhi360/Bosch_Shuttle3_BHI360_bsxsam_lite.fw.h"

namespace {
constexpr uint8_t kPressureSda = 11; // PA16 SERCOM1 on Feather M0
constexpr uint8_t kPressureScl = 13; // PA17 SERCOM1
constexpr uint8_t kTofSda = 28;      // PA12 SERCOM2
constexpr uint8_t kTofScl = 39;      // PA13 SERCOM2
constexpr uint8_t kPressureAddr = 0x68;
constexpr uint8_t kPressureConfig = 0x88;
constexpr uint32_t kPressurePeriodMs = 150;
constexpr uint32_t kPressureWaitMs = 110;
constexpr uint32_t kPressurePollMs = 10;
constexpr uint32_t kPressureDeadlineMs = 200;
constexpr uint32_t kTofPeriodMs = 100;
constexpr uint32_t kTofTimeoutMs = 100;
constexpr uint32_t kRetryMs = 2000;
constexpr uint8_t kReadLimit = 32;   // Bosch virtual-sensor presence array
constexpr uint8_t kWriteLimit = 28;  // conservative small packets
constexpr uint8_t kBhiChipRegister = 0x2B;
constexpr uint8_t kBhiChipExpected = 0x7A;
constexpr uint8_t kBmmChipRegister = 0x00;
constexpr uint8_t kBmmChipExpected = 0x33;

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
uint8_t wireStatus(TwoWire &bus, uint8_t address);
bool scanBus(TwoWire &bus, const char *name);

struct Imu {
  TwoWire &bus;
  uint8_t bhiAddr;
  uint8_t bmmAddr;
  const char *role;
  bhi360_dev dev = {};
  uint8_t fifo[256] = {};
  uint32_t lastPoll = 0;
  uint32_t lastSample = 0;
  uint32_t lastWarn = 0;
  uint32_t lastPrint = 0;
  bool ready = false;
  Imu(TwoWire &wire, uint8_t bhi, uint8_t bmm, const char *name)
      : bus(wire), bhiAddr(bhi), bmmAddr(bmm), role(name) {}
};
Imu head(pressureBus, 0x29, 0x15, "head");
Imu chest(tofBus, 0x28, 0x14, "chest");
uint8_t goodScans = 0;
bool idsVerified = false;

bool readRegister(TwoWire &bus, uint8_t address, uint8_t reg, uint8_t *data, uint8_t length) {
  if (!data || !length) return false;
  bus.beginTransmission(address);
  bus.write(reg);
  if (bus.endTransmission(false) != 0) return false;
  const size_t count = bus.requestFrom(address, length, static_cast<uint8_t>(true));
  if (count != length) {
    while (bus.available()) (void)bus.read();
    return false;
  }
  for (uint8_t i=0; i<length; ++i) {
    if (!bus.available()) return false;
    data[i] = static_cast<uint8_t>(bus.read());
  }
  return true;
}
bool identity(const Imu &node) {
  uint8_t bhiId = 0, tmp[3] = {};
  // A BMM350 I2C register read includes TWO leading dummy bytes.
  const bool okBhi = readRegister(node.bus, node.bhiAddr, kBhiChipRegister, &bhiId, 1);
  const bool okBmm = readRegister(node.bus, node.bmmAddr, kBmmChipRegister, tmp, 3);
  Serial.print("# IMU_ID role="); Serial.print(node.role);
  Serial.print(" bhi="); if (okBhi) Serial.print(bhiId, HEX); else Serial.print("read_error");
  Serial.print(" bmm="); if (okBmm) Serial.print(tmp[2], HEX); else Serial.print("read_error");
  const bool good = okBhi && okBmm && bhiId == kBhiChipExpected &&
                    tmp[2] == kBmmChipExpected;
  Serial.print(" valid="); Serial.println(good ? 1 : 0);
  return good;
}
void checkIds() {
  idsVerified = identity(head) && identity(chest);
  Serial.println(idsVerified ? "# FOUR_IMU_IDS_OK" : "# FOUR_IMU_IDS_FAILED");
}

int8_t busRead(uint8_t reg, uint8_t *data, uint32_t length, void *context) {
  Imu *node = static_cast<Imu *>(context);
  if (!node || !data || length == 0 || length > kReadLimit) {
    Serial.print("# IMU_IO_REJECT read_len="); Serial.println(length); return -1;
  }
  if (!readRegister(node->bus, node->bhiAddr, reg, data, static_cast<uint8_t>(length))) {
    Serial.print("# IMU_IO_FAIL read role="); Serial.print(node->role);
    Serial.print(" register=0x"); Serial.println(reg, HEX);
    return -1;
  }
  return 0;
}
int8_t busWrite(uint8_t reg, const uint8_t *data, uint32_t length, void *context) {
  Imu *node = static_cast<Imu *>(context);
  if (!node || !data || length == 0 || length > kWriteLimit) return -1;
  node->bus.beginTransmission(node->bhiAddr);
  if (node->bus.write(reg) != 1 ||
      node->bus.write(data, length) != length) return -1;
  const uint8_t result = node->bus.endTransmission(true);
  if (result) {
    Serial.print("# IMU_IO_FAIL write role="); Serial.print(node->role);
    Serial.print(" register=0x"); Serial.println(reg, HEX);
    return -1;
  }
  return 0;
}
void boschDelay(uint32_t usec, void *) {
  if (usec >= 1000) delay((usec + 999) / 1000);
  else delayMicroseconds(usec);
}
void onAccelerometer(const bhi360_fifo_parse_data_info *frame, void *context) {
  Imu *node = static_cast<Imu *>(context);
  if (!node || !frame || !frame->data_ptr || frame->data_size != 7) return;
  bhi360_event_data_xyz xyz = {};
  bhi360_event_data_parse_xyz(frame->data_ptr, &xyz);
  const uint32_t now = millis();
  node->lastSample = now;
  if (now - node->lastPrint < 100) return; // about 10 updates/s per IMU
  node->lastPrint = now;
  Serial.print("# accel,t_ms="); Serial.print(now);
  Serial.print(",sensor="); Serial.print(node->role);
  Serial.print(",x_raw="); Serial.print(xyz.x);
  Serial.print(",y_raw="); Serial.print(xyz.y);
  Serial.print(",z_raw="); Serial.print(xyz.z);
  Serial.println(",valid=1");
}
void imuError(const Imu &node, const char *stage, int code) {
  Serial.print("# IMU_FAULT role="); Serial.print(node.role);
  Serial.print(" stage="); Serial.print(stage);
  Serial.print(" code="); Serial.println(code);
}

bool bootImu(Imu &node) {
  node.ready = false;
  int8_t rc = bhi360_init(BHI360_I2C_INTERFACE, busRead, busWrite,
                          boschDelay, kWriteLimit, &node, &node.dev);
  if (rc != BHI360_OK) { imuError(node, "init", rc); return false; }
  uint8_t chip = 0;
  rc = bhi360_get_chip_id(&chip, &node.dev);
  if (rc != BHI360_OK || chip != BHI360_CHIP_ID) {
    imuError(node, "chip_id", rc); return false;
  }
  rc = bhi360_soft_reset(&node.dev);
  if (rc != BHI360_OK) { imuError(node, "reset", rc); return false; }
  delay(100);
  uint8_t boot = 0;
  rc = bhi360_get_boot_status(&boot, &node.dev);
  if (rc != BHI360_OK || !(boot & BHI360_BST_HOST_INTERFACE_READY)) {
    imuError(node, "host_not_ready", rc); return false;
  }
  rc = bhi360_set_host_interrupt_ctrl(
    BHI360_ICTL_DISABLE_STATUS_FIFO | BHI360_ICTL_DISABLE_DEBUG, &node.dev);
  if (rc != BHI360_OK) { imuError(node, "interrupt_config", rc); return false; }

  const uint32_t fwSize = sizeof(bhi360_firmware_image);
  Serial.print("# IMU_UPLOAD_START role="); Serial.print(node.role);
  Serial.print(" bytes="); Serial.println(fwSize);
  for (uint32_t pos = 0; pos < fwSize; pos += 24) {
    const uint32_t n = fwSize - pos < 24 ? fwSize - pos : 24;
    if (n % 4) { imuError(node, "image_alignment", -1); return false; }
    rc = bhi360_upload_firmware_to_ram_partly(
      &bhi360_firmware_image[pos], fwSize, pos, n, &node.dev);
    if (rc != BHI360_OK) {
      imuError(node, "firmware_upload", rc); return false;
    }
    if (pos % 12288 == 0) {
      Serial.print("# IMU_UPLOAD role="); Serial.print(node.role);
      Serial.print(" offset="); Serial.println(pos);
    }
  }
  rc = bhi360_boot_from_ram(&node.dev);
  if (rc != BHI360_OK) { imuError(node, "boot", rc); return false; }
  delay(250);
  uint16_t kernel = 0;
  rc = bhi360_get_kernel_version(&kernel, &node.dev);
  if (rc != BHI360_OK || !kernel) {
    imuError(node, "kernel", rc); return false;
  }
  Serial.print("# IMU_KERNEL role="); Serial.print(node.role);
  Serial.print(" version="); Serial.println(kernel);
  return true;
}
bool enableImu(Imu &node) {
  int8_t rc = bhi360_register_fifo_parse_callback(
      BHI360_SENSOR_ID_ACC, onAccelerometer, &node, &node.dev);
  if (rc != BHI360_OK) { imuError(node, "callback", rc); return false; }
  rc = bhi360_get_and_process_fifo(node.fifo, sizeof(node.fifo), &node.dev);
  if (rc != BHI360_OK) { imuError(node, "clear_fifo", rc); return false; }
  rc = bhi360_update_virtual_sensor_list(&node.dev);
  if (rc != BHI360_OK) { imuError(node, "virtual_sensor_list", rc); return false; }
  if (!bhi360_is_sensor_available(BHI360_SENSOR_ID_ACC, &node.dev)) {
    imuError(node, "accelerometer_unavailable", BHI360_E_PARAM_NOT_SET);
    return false;
  }
  bhi360_virtual_sensor_conf_param_conf config = {};
  config.sample_rate = 25.0f;
  config.latency = 0;
  rc = bhi360_virtual_sensor_conf_param_set_cfg(
      BHI360_SENSOR_ID_ACC, &config, &node.dev);
  if (rc != BHI360_OK) {
    imuError(node, "enable_accelerometer", rc); return false;
  }
  node.ready = true;
  node.lastPoll = millis();
  node.lastSample = millis();
  node.lastWarn = millis();
  node.lastPrint = 0;
  Serial.print("# IMU_READY role="); Serial.println(node.role);
  return true;
}
void startBothImus() {
  if (head.ready || chest.ready) {
    Serial.println("# IMU_ALREADY_STARTED"); return;
  }
  if (!usePressure || !useTof || goodScans < 2 || !idsVerified || acquisitionStarted) {
    Serial.println("# IMU_START_BLOCKED need c, two clean i, s, m before g");
    return;
  }
  if (!bootImu(head) || !bootImu(chest)) {
    Serial.println("# IMU_START_ABORTED reboot and inspect wiring");
    return;
  }
  if (!enableImu(head) || !enableImu(chest)) {
    head.ready = chest.ready = false;
    Serial.println("# IMU_START_ABORTED no valid dual stream");
  } else {
    Serial.println("# DUAL_IMU_READY head=A1 chest=B2 raw_accel_25hz");
  }
}
void serviceImu(Imu &node, uint32_t now) {
  if (!node.ready || now - node.lastPoll < 45) return;
  node.lastPoll = now;
  const int8_t rc = bhi360_get_and_process_fifo(node.fifo, sizeof(node.fifo), &node.dev);
  if (rc != BHI360_OK) {
    imuError(node, "read_fifo", rc);
    node.ready = false;
    return; // no stale values will be emitted as valid
  }
  if (now - node.lastSample > 2000 && now - node.lastWarn > 2000) {
    node.lastWarn = now;
    Serial.print("# IMU_STALE role="); Serial.println(node.role);
  }
}

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

bool scanBus(TwoWire &bus, const char *name) {
  Serial.print("# SCAN_START bus="); Serial.println(name);
  uint8_t count = 0;
  bool allExpected = true, aBhi=false, aBmm=false, pressure=false;
  bool bBhi=false, bBmm=false, range=false;
  const bool isA = &bus == &pressureBus;
  for (uint8_t addr=0x08; addr<=0x77; ++addr) {
    if (wireStatus(bus, addr) == 0) {
      ++count;
      Serial.print("# SCAN_FOUND bus="); Serial.print(name);
      Serial.print(" address=0x");
      if (addr < 16) Serial.print('0');
      Serial.println(addr, HEX);
      if (isA) {
        if (addr == head.bhiAddr) aBhi=true;
        else if (addr == head.bmmAddr) aBmm=true;
        else if (addr == kPressureAddr) pressure=true;
        else allExpected=false;
      } else {
        if (addr == chest.bhiAddr) bBhi=true;
        else if (addr == chest.bmmAddr) bBmm=true;
        else if (addr == vl6180x::ADDRESS) range=true;
        else allExpected=false;
      }
    }
  }
  Serial.print("# SCAN_END bus="); Serial.print(name);
  Serial.print(" count="); Serial.println(count);
  return allExpected && count == 3 &&
         (isA ? (aBhi && aBmm && pressure) : (bBhi && bBmm && range));
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
  Serial.println("# KEVIN FOUR PHYSICAL SENSORS v0.3 EXPERIMENTAL");
  Serial.println("# a=A2 only, b=B2 only, c=both; select once per cold setup");
  Serial.println("# i=full scan twice, s=verify IDs, m=boot both IMUs, g=pressure+ToF acquire");
  Serial.println("# Ports: A1 head BHI0x29 BMM0x15; A2 MCP3426 0x68; B1 VL6180X 0x29; B2 chest BHI0x28 BMM0x14");
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
  if (!head.ready || !chest.ready || !idsVerified || goodScans < 2) {
    Serial.println("# ACQUIRE_BLOCKED both IMUs must be ready, scan twice, s and m first");
    return;
  }
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
  else if (c == 's') { status(); checkIds(); }
  else if (c == 'm') startBothImus();
  else if (c == 'i') {
    if (usePressure && useTof) {
      const bool okA = scanBus(pressureBus, "A2");
      const bool okB = scanBus(tofBus, "B2");
      goodScans = okA && okB ? (goodScans < 3 ? goodScans + 1 : 3) : 0;
      idsVerified = false;
      Serial.print("# FOUR_SCAN_OK consecutive="); Serial.println(goodScans);
    } else Serial.println("# SELECT_BOTH_BUSES_FIRST c");
  } else if (c == 'g') startAcquisition();
  else if (c == 'p' && acquisitionStarted) {
    streaming = !streaming;
    pressurePending = false;  // discard any conversion from before the pause
    Serial.println(streaming ? "# STREAM_RUNNING" : "# STREAM_PAUSED");
  }
  if (streaming && usePressure) servicePressure(millis());
  if (streaming && useTof) serviceTof(millis());
  serviceImu(head, millis());
  serviceImu(chest, millis());
  delay(5);
}
