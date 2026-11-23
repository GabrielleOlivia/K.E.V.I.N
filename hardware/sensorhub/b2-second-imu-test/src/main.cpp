// K.E.V.I.N. SAMD21 SensorHub physical B2 IMU ONLY: address/ID and optional XYZ.
// TRAINING BENCH, not a medical device. Default SAFE build is read-only.
// BHI360 @ 0x28, BMM350 @ 0x14 on SERCOM2 (PA12 SDA / PA13 SCL).
#include <Arduino.h>
#include <Wire.h>
#include "wiring_private.h"

#ifndef KEVIN_ID_ONLY
#include "bhi360.h"
#include "bhi360_event_data.h"
#include "bhi360_virtual_sensor_conf_param.h"
#include "bhi360/Bosch_Shuttle3_BHI360_bsxsam_lite.fw.h"
#endif

namespace {
constexpr uint8_t SDA_PIN = 28; // PA12, Feather M0 Express variant
constexpr uint8_t SCL_PIN = 39; // PA13, Feather M0 Express variant
constexpr uint8_t BHI_ADDR = 0x28;
constexpr uint8_t BMM_ADDR = 0x14;
constexpr uint8_t BHI_CHIP_ID_REG = 0x2B;
constexpr uint8_t BHI_CHIP_ID = 0x7A;
constexpr uint8_t BMM_CHIP_ID_REG = 0x00;
constexpr uint8_t BMM_CHIP_ID = 0x33;
// The Bosch virtual-sensor presence parameter has a 32-byte response.
// SAMD21 Adafruit Wire uses a 256-byte RX ring buffer, so a 32-byte READ fits.
// The previous 28-byte read guard rejected that mandatory transfer (I/O -3).
constexpr uint8_t MAX_XFER = 28; // SDK chunk size and conservative write bound
constexpr uint8_t MAX_READ = 32; // required for the virtual-sensor presence query
TwoWire imuBus(&sercom2, SDA_PIN, SCL_PIN);
bool wireStarted = false;
bool idsValid = false;

bool expectedPin(uint8_t pin, uint8_t port, uint8_t number) {
  return pin < PINS_COUNT && g_APinDescription[pin].ulPort == port &&
         g_APinDescription[pin].ulPin == number;
}
bool muxIsSercomC(uint8_t index) {
  const auto &desc = g_APinDescription[index];
  const auto &port = PORT->Group[desc.ulPort];
  const uint8_t pin = desc.ulPin;
  const uint8_t shift = (pin & 1) ? 4 : 0;
  return port.PINCFG[pin].bit.PMUXEN &&
         ((port.PMUX[pin / 2].reg >> shift) & 0x0f) == PIO_SERCOM;
}
bool startBus() {
  if (!expectedPin(SDA_PIN, PORTA, 12) || !expectedPin(SCL_PIN, PORTA, 13)) {
    Serial.println("# STOP PINMAP_MISMATCH"); return false;
  }
  pinMode(SDA_PIN, INPUT);
  pinMode(SCL_PIN, INPUT);
  delay(3);
  if (digitalRead(SDA_PIN) == LOW || digitalRead(SCL_PIN) == LOW) {
    Serial.println("# STOP BUS_B_IDLE_LINE_LOW"); return false;
  }
  imuBus.begin();
  if (pinPeripheral(SDA_PIN, PIO_SERCOM) != 0 ||
      pinPeripheral(SCL_PIN, PIO_SERCOM) != 0 ||
      !muxIsSercomC(SDA_PIN) || !muxIsSercomC(SCL_PIN)) {
    Serial.println("# STOP PINMUX_MISMATCH"); return false;
  }
  imuBus.setClock(100000);
  return true;
}

int wireAck(uint8_t addr) {
  imuBus.beginTransmission(addr);
  return imuBus.endTransmission(true);
}
// BHI360 one-byte register read: register index + repeated-start + value.
bool bhiReadId(uint8_t &value) {
  imuBus.beginTransmission(BHI_ADDR);
  imuBus.write(BHI_CHIP_ID_REG);
  if (imuBus.endTransmission(false) != 0) return false;
  if (imuBus.requestFrom(BHI_ADDR, (uint8_t)1, (uint8_t)true) != 1) return false;
  value = (uint8_t)imuBus.read();
  return true;
}
// BMM350 has TWO leading dummy bytes on every I2C register read.
bool bmmReadId(uint8_t &value) {
  imuBus.beginTransmission(BMM_ADDR);
  imuBus.write(BMM_CHIP_ID_REG);
  if (imuBus.endTransmission(false) != 0) return false;
  if (imuBus.requestFrom(BMM_ADDR, (uint8_t)3, (uint8_t)true) != 3) return false;
  (void)imuBus.read(); // dummy byte 1
  (void)imuBus.read(); // dummy byte 2
  value = (uint8_t)imuBus.read();
  return true;
}

bool scanExpectedOnly() {
  Serial.println("# SCAN_START bus=B2");
  uint8_t count = 0;
  bool foundBHI = false, foundBMM = false, unexpected = false;
  for (uint8_t addr = 0x08; addr <= 0x77; ++addr) {
    if (wireAck(addr) == 0) {
      ++count;
      Serial.print("# SCAN_FOUND bus=B2 address=0x");
      if (addr < 16) Serial.print('0');
      Serial.println(addr, HEX);
      if (addr == BHI_ADDR) foundBHI = true;
      else if (addr == BMM_ADDR) foundBMM = true;
      else unexpected = true;
    }
  }
  Serial.print("# SCAN_END bus=B2 count="); Serial.println(count);
  if (unexpected || !foundBHI || !foundBMM || count != 2) {
    Serial.println("# STOP B2_SCAN_UNEXPECTED do not initialize");
    return false;
  }
  return true;
}

bool checkIdentities() {
  idsValid = false;
  if (!scanExpectedOnly()) return false;
  uint8_t bhi = 0, bmm = 0;
  bool bhiOK = bhiReadId(bhi);
  bool bmmOK = bmmReadId(bmm);
  Serial.print("# BHI360_B2 chip_id=");
  if (bhiOK) { Serial.print("0x"); Serial.print(bhi, HEX); }
  else Serial.print("READ_FAILED");
  Serial.println(" expected=0x7A");
  Serial.print("# BMM350_B2 chip_id=");
  if (bmmOK) { Serial.print("0x"); Serial.print(bmm, HEX); }
  else Serial.print("READ_FAILED");
  Serial.println(" expected=0x33");
  idsValid = bhiOK && bmmOK && bhi == BHI_CHIP_ID && bmm == BMM_CHIP_ID;
  Serial.println(idsValid ? "# B2_IMU_IDENTIFIED BOTH_CHIPS" :
                            "# STOP B2_ID_MISMATCH check wiring and read path");
  return idsValid;
}

#ifndef KEVIN_ID_ONLY
static bhi360_dev bhi = {};
static uint8_t fifo[256] = {};
bool stream = false;
uint32_t lastPoll = 0;
uint32_t lastSample = 0;
uint32_t lastReport = 0;

int8_t readBosch(uint8_t reg, uint8_t *data, uint32_t len, void *) {
  if (!data || len == 0 || len > MAX_READ) {
    Serial.print("# IMU_I2C_READ_REJECT reg=0x");
    Serial.print(reg, HEX);
    Serial.print(" len=");
    Serial.println(len);
    return -1;
  }
  imuBus.beginTransmission(BHI_ADDR);
  imuBus.write(reg);
  if (imuBus.endTransmission(false) != 0) return -1;
  const size_t received = imuBus.requestFrom(BHI_ADDR, (uint8_t)len, (uint8_t)true);
  if (received != len) {
    Serial.print("# IMU_I2C_READ_SHORT reg=0x");
    Serial.print(reg, HEX);
    Serial.print(" requested=");
    Serial.print(len);
    Serial.print(" received=");
    Serial.println(received);
    while (imuBus.available()) (void)imuBus.read();
    return -1;
  }
  for (uint32_t i=0; i<len; ++i) {
    if (!imuBus.available()) return -1;
    data[i] = (uint8_t)imuBus.read();
  }
  return 0;
}
int8_t writeBosch(uint8_t reg, const uint8_t *data, uint32_t len, void *) {
  if (!data || len == 0 || len > MAX_XFER) return -1;
  imuBus.beginTransmission(BHI_ADDR);
  if (imuBus.write(reg) != 1 || imuBus.write(data, len) != len) return -1;
  return imuBus.endTransmission(true) == 0 ? 0 : -1;
}
void boschDelay(uint32_t us, void *) {
  if (us >= 1000) delay((us + 999) / 1000);
  else delayMicroseconds(us);
}
void onAccel(const bhi360_fifo_parse_data_info *info, void *) {
  if (!info || !info->data_ptr || info->data_size != 7) return;
  bhi360_event_data_xyz vec = {};
  bhi360_event_data_parse_xyz(info->data_ptr, &vec);
  lastSample = millis();
  // Approx. 10 Hz display, though underlying ODR is 25 Hz.
  if (lastSample - lastReport < 100) return;
  lastReport = lastSample;
  Serial.print("# accel,t_ms="); Serial.print(lastSample);
  Serial.print(",x_raw="); Serial.print(vec.x);
  Serial.print(",y_raw="); Serial.print(vec.y);
  Serial.print(",z_raw="); Serial.print(vec.z);
  Serial.println(",valid=1,sensor=BHI360_B2");
}
void fail(const char *stage, int err) {
  Serial.print("# IMU_FAULT stage="); Serial.print(stage);
  Serial.print(" code="); Serial.println(err);
}
void startAcceleration() {
  if (stream) { Serial.println("# IMU_ALREADY_RUNNING"); return; }
  if (!checkIdentities()) return; // no firmware writes until two real chip IDs pass
  Serial.println("# IMU_FIRMWARE_START B2 BHI360@0x28 experimental");
  int8_t rc = bhi360_init(BHI360_I2C_INTERFACE, readBosch, writeBosch,
                           boschDelay, MAX_XFER, nullptr, &bhi);
  if (rc != BHI360_OK) { fail("init", rc); return; }
  uint8_t id = 0;
  rc = bhi360_get_chip_id(&id, &bhi);
  if (rc != BHI360_OK || id != BHI360_CHIP_ID) { fail("bosch_id", rc); return; }
  rc = bhi360_soft_reset(&bhi);
  if (rc != BHI360_OK) { fail("reset", rc); return; }
  delay(100);
  uint8_t boot = 0;
  rc = bhi360_get_boot_status(&boot, &bhi);
  if (rc != BHI360_OK || !(boot & BHI360_BST_HOST_INTERFACE_READY)) {
    fail("host_not_ready", rc); return;
  }
  rc = bhi360_set_host_interrupt_ctrl(
      BHI360_ICTL_DISABLE_STATUS_FIFO | BHI360_ICTL_DISABLE_DEBUG, &bhi);
  if (rc != BHI360_OK) { fail("interrupt_config", rc); return; }
  const uint32_t firmwareSize = sizeof(bhi360_firmware_image);
  // Bosch's chunked upload; packet multiple of 4, fits SAMD21 Wire TX buffer.
  for (uint32_t pos=0; pos<firmwareSize; pos+=24) {
    if (firmwareSize - pos < 24) { // Bosch firmware images should be 4-byte aligned
      if ((firmwareSize - pos) % 4 != 0) { fail("image_alignment", -1); return; }
    }
    const uint32_t length = (firmwareSize - pos < 24) ? firmwareSize - pos : 24;
    rc = bhi360_upload_firmware_to_ram_partly(
      &bhi360_firmware_image[pos], firmwareSize, pos, length, &bhi);
    if (rc != BHI360_OK) { fail("firmware_upload", rc); return; }
    if (pos % 3072 == 0) {
      Serial.print("# IMU_UPLOAD bytes="); Serial.print(pos);
      Serial.print(" total="); Serial.println(firmwareSize);
    }
  }
  rc = bhi360_boot_from_ram(&bhi);
  if (rc != BHI360_OK) { fail("boot", rc); return; }
  delay(250);
  uint16_t kernel = 0;
  rc = bhi360_get_kernel_version(&kernel, &bhi);
  if (rc != BHI360_OK || kernel == 0) { fail("kernel_version", rc); return; }
  rc = bhi360_register_fifo_parse_callback(
      BHI360_SENSOR_ID_ACC, onAccel, nullptr, &bhi);
  if (rc != BHI360_OK) { fail("callback", rc); return; }
  rc = bhi360_get_and_process_fifo(fifo, sizeof(fifo), &bhi);
  if (rc != BHI360_OK) { fail("initial_fifo", rc); return; }
  rc = bhi360_update_virtual_sensor_list(&bhi);
  if (rc != BHI360_OK) {
    // An SDK I/O failure is not evidence that the accelerometer is absent.
    fail("virtual_sensor_list_io", rc); return;
  }
  const uint8_t available = bhi360_is_sensor_available(BHI360_SENSOR_ID_ACC, &bhi);
  Serial.print("# IMU_SENSOR_LIST_READY accel_available=");
  Serial.println(available ? 1 : 0);
  if (!available) {
    fail("accelerometer_not_available", BHI360_E_PARAM_NOT_SET); return;
  }
  bhi360_virtual_sensor_conf_param_conf cfg = {};
  cfg.sample_rate = 25.0f;
  cfg.latency = 0;
  rc = bhi360_virtual_sensor_conf_param_set_cfg(BHI360_SENSOR_ID_ACC, &cfg, &bhi);
  if (rc != BHI360_OK) { fail("enable_accelerometer", rc); return; }
  stream = true;
  lastPoll = millis();
  lastSample = 0;
  lastReport = 0;
  Serial.print("# IMU_READY B2 accel_virtual_sensor=4 kernel="); Serial.println(kernel);
  Serial.println("# IMU_NOTE xyz are raw signed samples, NOT yet calibrated to g or angle");
}
void serviceAcceleration() {
  if (!stream) return;
  const uint32_t now = millis();
  if (now - lastPoll < 50) return;
  lastPoll = now;
  const int8_t rc = bhi360_get_and_process_fifo(fifo, sizeof(fifo), &bhi);
  if (rc != BHI360_OK) {
    fail("read_fifo", rc);
    stream = false;
    return;
  }
  if (now - lastSample > 2000) {
    if (now - lastReport >= 2000) {
      lastReport = now;
      Serial.println("# IMU_WAITING no fresh accel samples");
    }
  }
}
#endif

void help() {
  Serial.println("# KEVIN B2 IMU TEST v1 BHI360@0x28 BMM350@0x14");
#ifdef KEVIN_ID_ONLY
  Serial.println("# BUILD=READ_ONLY_ID; i=scan; s=chip IDs; h=help; no sensor boot writes");
#else
  Serial.println("# BUILD=EXPERIMENTAL_ACCEL; i=scan; s=chip IDs; m=start accel; h=help");
#endif
  Serial.println("# Physical B2 only. NO ToF/pressure attached. Do NOT use old 'g'.");
}
} // namespace

void SERCOM2_Handler() { imuBus.onService(); }
void setup() {
  Serial.begin(115200);
  const uint32_t started = millis();
  while (!Serial && millis() - started < 4000) delay(10);
  help();
  wireStarted = startBus();
  if (!wireStarted) { while (true) delay(1000); }
  Serial.println("# B2_BUS_READY send i then s");
}
void loop() {
  if (Serial.available()) {
    const char c = Serial.read();
    if (c == 'i') (void)scanExpectedOnly();
    else if (c == 's') (void)checkIdentities();
    else if (c == 'h' || c == '?') help();
#ifndef KEVIN_ID_ONLY
    else if (c == 'm') startAcceleration();
#endif
  }
#ifndef KEVIN_ID_ONLY
  serviceAcceleration();
#endif
  delay(5);
}
