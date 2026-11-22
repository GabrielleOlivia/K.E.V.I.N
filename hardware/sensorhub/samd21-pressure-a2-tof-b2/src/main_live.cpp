// K.E.V.I.N. EXPERIMENTAL LIVE I2C: A1 BHI360, A2 pressure, physical B1 ToF.
// Bench diagnostics only: ADC counts are NOT calibrated pressure; mm are raw ToF distances.
// Wiring changes only with USB disconnected. Pressure MCP3426 0x68 on SERCOM1,
// VL6180X 0x29 on SERCOM2; BHI360 0x29 on A1 (EXPERIMENTAL, opt-in 'm').
#include <Arduino.h>
#include <Wire.h>
#include "wiring_private.h"
#include "vl6180x.h"
#include "bench_command.h"
#include <math.h>
#include "bhi360.h"
#include "bhi360_event_data.h"
#include "bhi360_parse.h"
#include "bhi360_virtual_sensor_conf_param.h"
#include "bhi360/Bosch_Shuttle3_BHI360_bsxsam.fw.h"


namespace {
constexpr uint8_t kPressureSda = 11; // Feather M0 index for PA16, SERCOM1
constexpr uint8_t kPressureScl = 13; // Feather M0 index for PA17, SERCOM1
constexpr uint8_t kTofSda = 28;     // Feather M0 index for PA12, SERCOM2
constexpr uint8_t kTofScl = 39;     // Feather M0 index for PA13, SERCOM2
constexpr uint8_t kPressureAddr = 0x68;
constexpr uint8_t kPressureConfig = 0x88; // MCP3426 CH1 one-shot, 16bit, gain 1
constexpr uint32_t kPressurePeriodMs = 150; // experimental live refresh, NOT bench-verified
constexpr uint32_t kPressureWaitMs = 110;
constexpr uint32_t kPressurePollMs = 10;
constexpr uint32_t kPressureDeadlineMs = 200;
constexpr uint32_t kTofPeriodMs = 100; // experimental live refresh, NOT bench-verified
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
uint8_t wireStatus(TwoWire &bus, uint8_t address);
constexpr uint8_t kImuAddr = 0x29; // physical A1; BHI360 address verified in bench scan
constexpr uint16_t kBhiMaxXfer = 28; // Wire tx buffer: 1-byte register + <=28 bytes
static bhi360_dev imuDevice = {};
static uint8_t imuFifoBuffer[256] = {};
bool imuStarted = false;
bool imuHavePitch = false;
float imuNativePitch = 0;
float imuPitchZero = 0;
int8_t imuPitchSign = 1;  // reverse with 'f' after comparing known physical flexion
uint32_t imuLastSample = 0;
uint32_t imuLastPoll = 0;
uint32_t imuLastStale = 0;

// The BHI360 requires its Bosch firmware and FIFO virtual sensor configuration.
// This implementation intentionally uses Bosch's BSD-licensed SensorAPI, not
// guessed raw registers; it remains EXPERIMENTAL until built and tested.
static int8_t imuBusRead(uint8_t reg, uint8_t *out, uint32_t length, void *) {
  if (!out || length == 0 || length > kBhiMaxXfer) return -1;
  pressureBus.beginTransmission(kImuAddr);
  pressureBus.write(reg);
  if (pressureBus.endTransmission(false) != 0) return -1;
  const uint8_t count = pressureBus.requestFrom(kImuAddr, static_cast<uint8_t>(length),
                                                 static_cast<uint8_t>(true));
  if (count != length) {
    while (pressureBus.available()) pressureBus.read();
    return -1;
  }
  for (uint32_t i = 0; i < length; ++i) {
    if (!pressureBus.available()) return -1;
    out[i] = static_cast<uint8_t>(pressureBus.read());
  }
  return 0;
}

static int8_t imuBusWrite(uint8_t reg, const uint8_t *data, uint32_t length, void *) {
  if (!data || length == 0 || length > kBhiMaxXfer) return -1;
  pressureBus.beginTransmission(kImuAddr);
  if (pressureBus.write(reg) != 1) return -1;
  if (pressureBus.write(data, length) != length) return -1;
  return pressureBus.endTransmission(true) == 0 ? 0 : -1;
}

static void imuDelayUs(uint32_t us, void *) {
  if (us >= 1000) delay((us + 999) / 1000);
  else delayMicroseconds(us);
}
static float wrapPitch(float deg) {
  while (deg > 180.0f) deg -= 360.0f;
  while (deg < -180.0f) deg += 360.0f;
  return deg;
}
static void imuEulerCallback(const bhi360_fifo_parse_data_info *frame, void *) {
  if (!frame || frame->data_size != 7 || !frame->data_ptr) return;
  bhi360_event_data_orientation e = {};
  bhi360_event_data_parse_orientation(frame->data_ptr, &e);
  const float nativePitch = e.pitch * (360.0f / 32768.0f);
  if (!isfinite(nativePitch)) return;
  if (!imuHavePitch) {
    imuPitchZero = nativePitch; // initial neutral reference (must be verified)
    imuHavePitch = true;
    Serial.println("# IMU_ZERO_AUTO first valid orientation sample: verify neutral pose");
  }
  imuNativePitch = nativePitch;
  imuLastSample = millis();
  const float relative = wrapPitch(nativePitch - imuPitchZero) * imuPitchSign;
  Serial.print("# imu,head_pitch_deg=");
  Serial.print(relative, 2);
  Serial.print(",valid=1,source=bhi360,raw_pitch_deg=");
  Serial.println(nativePitch, 2);
}
static void imuFailure(const char *stage, int error) {
  Serial.print("# IMU_FAULT stage=");
  Serial.print(stage);
  Serial.print(" code=");
  Serial.println(error);
}
static void startImu() {
  if (imuStarted) { Serial.println("# IMU_ALREADY_STARTED"); return; }
  if (!usePressure) { Serial.println("# IMU_NEEDS_A_BUS select c after cold reset"); return; }
  if (acquisitionStarted) {
    Serial.println("# IMU_START_BLOCKED acquire already running; reboot, select c, then m before g");
    return;
  }
  // Refuse to boot on stale wiring or a disconnected shared bus.
  if (wireStatus(pressureBus, kImuAddr) != 0 || wireStatus(pressureBus, kPressureAddr) != 0 ||
      !useTof || wireStatus(tofBus, vl6180x::ADDRESS) != 0) {
    Serial.println("# IMU_START_BLOCKED expected A1=0x29 A2=0x68 B1=0x29; scan i first");
    return;
  }
  Serial.println("# IMU_START BHI360 Bosch SensorAPI, firmware upload experimental");
  int8_t rc = bhi360_init(BHI360_I2C_INTERFACE, imuBusRead, imuBusWrite,
                           imuDelayUs, kBhiMaxXfer, nullptr, &imuDevice);
  if (rc != BHI360_OK) { imuFailure("init", rc); return; }
  uint8_t id = 0;
  rc = bhi360_get_chip_id(&id, &imuDevice);
  if (rc != BHI360_OK || id != BHI360_CHIP_ID) {
    Serial.print("# IMU_WRONG_CHIP_ID read=0x");
    Serial.println(id, HEX);
    imuFailure("chip_id", rc); return;
  }
  rc = bhi360_soft_reset(&imuDevice);
  if (rc != BHI360_OK) { imuFailure("soft_reset", rc); return; }
  delay(100);
  uint8_t boot = 0;
  rc = bhi360_get_boot_status(&boot, &imuDevice);
  if (rc != BHI360_OK || !(boot & BHI360_BST_HOST_INTERFACE_READY)) {
    imuFailure("boot_status", rc); return;
  }
  rc = bhi360_set_host_interrupt_ctrl(
      BHI360_ICTL_DISABLE_STATUS_FIFO | BHI360_ICTL_DISABLE_DEBUG, &imuDevice);
  if (rc != BHI360_OK) { imuFailure("irq_config", rc); return; }

  // Upload in small packets; the entire image is const and resides in MCU flash.
  const uint32_t size = sizeof(bhi360_firmware_image);
  constexpr uint32_t packet = 24; // multiple of 4, fits the SAMD21 Wire TX buffer
  for (uint32_t pos = 0; pos < size; pos += packet) {
    const uint32_t length = size - pos < packet ? size - pos : packet;
    rc = bhi360_upload_firmware_to_ram_partly(
      &bhi360_firmware_image[pos], size, pos, length, &imuDevice);
    if (rc != BHI360_OK) { imuFailure("fw_upload", rc); return; }
    if (pos % 4096 == 0) {
      Serial.print("# IMU_UPLOAD_PROGRESS bytes="); Serial.print(pos);
      Serial.print(" total="); Serial.println(size);
    }
  }
  rc = bhi360_boot_from_ram(&imuDevice);
  if (rc != BHI360_OK) { imuFailure("boot_from_ram", rc); return; }
  delay(400);
  uint16_t kernel = 0;
  rc = bhi360_get_kernel_version(&kernel, &imuDevice);
  if (rc != BHI360_OK || kernel == 0) { imuFailure("kernel", rc); return; }

  rc = bhi360_register_fifo_parse_callback(
      BHI360_SENSOR_ID_ORI_WU, imuEulerCallback, nullptr, &imuDevice);
  if (rc != BHI360_OK) { imuFailure("register_callback", rc); return; }
  rc = bhi360_get_and_process_fifo(imuFifoBuffer, sizeof(imuFifoBuffer), &imuDevice);
  if (rc != BHI360_OK) { imuFailure("clear_fifo", rc); return; }
  rc = bhi360_update_virtual_sensor_list(&imuDevice);
  if (rc != BHI360_OK) { imuFailure("sensor_list", rc); return; }
  if (!bhi360_is_sensor_available(BHI360_SENSOR_ID_ORI_WU, &imuDevice)) {
    Serial.println("# IMU_FAULT orientation virtual sensor unavailable in firmware"); return;
  }
  bhi360_virtual_sensor_conf_param_conf cfg = {};
  cfg.sample_rate = 10.0f;
  cfg.latency = 0;
  rc = bhi360_virtual_sensor_conf_param_set_cfg(
      BHI360_SENSOR_ID_ORI_WU, &cfg, &imuDevice);
  if (rc != BHI360_OK) { imuFailure("enable_euler", rc); return; }
  imuStarted = true;
  imuHavePitch = false;
  imuLastPoll = millis();
  Serial.print("# IMU_READY firmware_booted=1 kernel=");
  Serial.print(kernel);
  Serial.println(" stream=euler_10hz awaiting=first_sample");
}
static void serviceImu(uint32_t now) {
  if (!imuStarted || now - imuLastPoll < 70) return;
  imuLastPoll = now;
  const int8_t rc = bhi360_get_and_process_fifo(imuFifoBuffer, sizeof(imuFifoBuffer),
                                                &imuDevice);
  if (rc != BHI360_OK) {
    imuFailure("fifo", rc);
    imuStarted = false;
    imuHavePitch = false; return;
  }
  if ((!imuHavePitch || now - imuLastSample > 2000) && now - imuLastStale > 2000) {
    imuLastStale = now;
    Serial.println("# imu,valid=0,status=waiting_or_stale");
  }
}
static void imuZero() {
  if (!imuHavePitch || millis() - imuLastSample > 1500) {
    Serial.println("# IMU_ZERO_FAIL no fresh pitch"); return;
  }
  imuPitchZero = imuNativePitch;
  Serial.println("# IMU_ZERO_OK neutral head reference set");
}
static void imuFlip() {
  imuPitchSign = -imuPitchSign;
  Serial.print("# IMU_SIGN=");
  Serial.println(imuPitchSign);
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
  Serial.println("# KEVIN SAMD21 A2+B2 review v1");
  Serial.println("# a=A2 only, b=B2 only, c=both; select once per cold setup");
  Serial.println("# s=target ACK/status, i=scan, m=start BHI360 EXPERIMENTAL, z=zero tilt, f=flip tilt sign");
  Serial.println("# g=pressure/ToF acquire, p=pause, h=help; physical ports A1 IMU A2 pressure B1 ToF");
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
  else if (c == 'm') startImu();
  else if (c == 'z') imuZero();
  else if (c == 'f') imuFlip();
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
  serviceImu(millis());
  delay(5);
}
