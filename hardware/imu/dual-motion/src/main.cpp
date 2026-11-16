// K.E.V.I.N. / Experimental dual BHI360 Game Rotation Vector stream.
// RobotPatient SAMD21 SensorHub: A1=chest (SERCOM1), B1=head (SERCOM2).
// The two IMUs may both use I2C address 0x29 because they occupy separate buses.
// Requires official Bosch BHI360 SensorAPI v2.3.1, installed by scripts/setup-bosch.ps1.
// For manikin simulation/research only; NOT for patient care or clinical assessment.

#include <Arduino.h>
#include <Wire.h>
#include <math.h>
#include "wiring_private.h"

extern "C" {
#include "bhi360.h"
#include "bhi360_virtual_sensor_conf_param.h"
#include "bhi360_event_data.h"
}
#include "bhi360/Bosch_Shuttle3_BHI360_bsxsam.fw.h"

namespace {
constexpr uint8_t SDA_A = 11;  // PA16 (existing successful diagnostic)
constexpr uint8_t SCL_A = 13;  // PA17
constexpr uint8_t SDA_B = 28;  // PA12
constexpr uint8_t SCL_B = 39;  // PA13
constexpr uint8_t SENSOR_ADDRESS = 0x29;  // verified on both devices
constexpr uint8_t FUSER2_ID_REG = 0x1C;
constexpr uint8_t FUSER2_ID_EXPECTED = 0x89; // verified with existing probe
constexpr uint32_t SAMPLE_INTERVAL_MS = 25; // poll each at ~40Hz, configured 25Hz
constexpr uint32_t PRINT_INTERVAL_MS = 100; // print latest snapshots at up to 10Hz
constexpr size_t FIFO_BUFFER_SIZE = 512;

TwoWire busA(&sercom1, SDA_A, SCL_A);
TwoWire busB(&sercom2, SDA_B, SCL_B);
uint8_t fifoBuffer[FIFO_BUFFER_SIZE];

struct Imu {
  const char* label;
  TwoWire* wire;
  bhi360_dev dev;
  bool ready;
  bool hasQuaternion;
  float x, y, z, w;
  float accuracyRad;
  uint32_t lastMotionMs;
  uint32_t errorCount;
};
Imu chest = {"CHEST", &busA, {}, false, false, 0, 0, 0, 1, 0, 0, 0};
Imu head  = {"HEAD",  &busB, {}, false, false, 0, 0, 0, 1, 0, 0, 0};

bool pinsMatch(uint8_t idx, uint32_t port, uint32_t pin) {
  return g_APinDescription[idx].ulPort == port && g_APinDescription[idx].ulPin == pin;
}

bool readChipId(TwoWire& wire, uint8_t& id) {
  wire.beginTransmission(SENSOR_ADDRESS);
  wire.write(FUSER2_ID_REG);
  if (wire.endTransmission(false) != 0) return false;
  if (wire.requestFrom(SENSOR_ADDRESS, static_cast<uint8_t>(1), static_cast<uint8_t>(true)) != 1) return false;
  id = static_cast<uint8_t>(wire.read());
  return true;
}

// Bosch callback. The register is sent as the I2C register pointer (no SPI masking).
int8_t boschRead(uint8_t reg, uint8_t *data, uint32_t len, void *context) {
  auto* imu = static_cast<Imu*>(context);
  if (!imu || !data || !len || len > 28) return -1;
  TwoWire& wire = *imu->wire;
  wire.beginTransmission(SENSOR_ADDRESS);
  wire.write(reg);
  if (wire.endTransmission(false) != 0) return -1;
  const uint8_t requested = static_cast<uint8_t>(len);
  if (wire.requestFrom(SENSOR_ADDRESS, requested, static_cast<uint8_t>(true)) != requested) {
    while (wire.available()) wire.read();
    return -1;
  }
  for (uint32_t i = 0; i < len; ++i) data[i] = static_cast<uint8_t>(wire.read());
  return 0;
}

int8_t boschWrite(uint8_t reg, const uint8_t *data, uint32_t len, void *context) {
  auto* imu = static_cast<Imu*>(context);
  if (!imu || (len && !data) || len > 28) return -1;
  TwoWire& wire = *imu->wire;
  wire.beginTransmission(SENSOR_ADDRESS);
  wire.write(reg);
  if (len && wire.write(data, len) != len) { wire.endTransmission(true); return -1; }
  return wire.endTransmission(true) == 0 ? 0 : -1;
}

void boschDelay(uint32_t microseconds, void*) {
  // delayMicroseconds() is not intended for large values on all Arduino cores.
  while (microseconds >= 1000) { delay(1); microseconds -= 1000; }
  if (microseconds) delayMicroseconds(microseconds);
}

void onQuaternion(const bhi360_fifo_parse_data_info* info, void* context) {
  auto* imu = static_cast<Imu*>(context);
  if (!imu || !info || info->data_size != 11) return;
  bhi360_event_data_quaternion q{};
  bhi360_event_data_parse_quaternion(info->data_ptr, &q);
  imu->x = q.x / 16384.0f;
  imu->y = q.y / 16384.0f;
  imu->z = q.z / 16384.0f;
  imu->w = q.w / 16384.0f;
  imu->accuracyRad = q.accuracy / 16384.0f;
  imu->lastMotionMs = millis();
  imu->hasQuaternion = true;
}

bool checked(const char* operation, int8_t result, const Imu& imu) {
  Serial.print("# "); Serial.print(imu.label); Serial.print(' ');
  Serial.print(operation); Serial.print(" result="); Serial.println(static_cast<int>(result));
  return result == BHI360_OK;
}

bool initImu(Imu& imu) {
  uint8_t id = 0;
  if (!readChipId(*imu.wire, id) || id != FUSER2_ID_EXPECTED) {
    Serial.print("# "); Serial.print(imu.label);
    Serial.println(" STOP: expected FUSER2_ID 0x89 at address 0x29");
    return false; // do not write configuration to unknown I2C devices
  }
  Serial.print("# "); Serial.print(imu.label); Serial.println(" BHI360 ID verified");

  // The SAMD21 Wire TX buffer is 32 bytes. Bosch API is limited to 28 data bytes
  // per transaction; one additional byte is required for register address.
  if (!checked("api_init", bhi360_init(BHI360_I2C_INTERFACE, boschRead, boschWrite,
                                       boschDelay, 28, &imu, &imu.dev), imu)) return false;
  if (!checked("soft_reset", bhi360_soft_reset(&imu.dev), imu)) return false;
  delay(120);
  if (!checked("interrupt_setup", bhi360_set_host_interrupt_ctrl(
      BHI360_ICTL_DISABLE_STATUS_FIFO | BHI360_ICTL_DISABLE_DEBUG, &imu.dev), imu)) return false;
  if (!checked("interface_setup", bhi360_set_host_intf_ctrl(0, &imu.dev), imu)) return false;
  uint8_t boot = 0;
  if (!checked("boot_status", bhi360_get_boot_status(&boot, &imu.dev), imu)) return false;
  Serial.print("# "); Serial.print(imu.label); Serial.print(" boot=0x"); Serial.println(boot, HEX);
  if (!(boot & BHI360_BST_HOST_INTERFACE_READY)) {
    Serial.println("# Host interface not ready; aborting firmware upload");
    return false;
  }

  Serial.print("# "); Serial.print(imu.label);
  Serial.print(" loading "); Serial.print(sizeof(bhi360_firmware_image));
  Serial.println(" firmware bytes to BHI360 RAM; do not disconnect USB");
  if (!checked("firmware_upload", bhi360_upload_firmware_to_ram(
      bhi360_firmware_image, sizeof(bhi360_firmware_image), &imu.dev), imu)) return false;
  if (!checked("boot_from_ram", bhi360_boot_from_ram(&imu.dev), imu)) return false;
  uint16_t kernel = 0;
  if (!checked("kernel_version", bhi360_get_kernel_version(&kernel, &imu.dev), imu)) return false;
  Serial.print("# "); Serial.print(imu.label); Serial.print(" kernel="); Serial.println(kernel);
  if (kernel == 0) return false;

  if (!checked("callback", bhi360_register_fifo_parse_callback(
      BHI360_SENSOR_ID_GAMERV, onQuaternion, &imu, &imu.dev), imu)) return false;
  if (!checked("initial_fifo", bhi360_get_and_process_fifo(
      fifoBuffer, sizeof(fifoBuffer), &imu.dev), imu)) return false;
  if (!checked("sensor_list", bhi360_update_virtual_sensor_list(&imu.dev), imu)) return false;
  bhi360_virtual_sensor_conf_param_conf conf{};
  conf.sample_rate = 25.0f;
  conf.latency = 0;
  if (!checked("enable_game_rotation_vector", bhi360_virtual_sensor_conf_param_set_cfg(
      BHI360_SENSOR_ID_GAMERV, &conf, &imu.dev), imu)) return false;
  imu.ready = true;
  return true;
}

void printSample(const Imu& imu, uint32_t now) {
  if (!imu.hasQuaternion) return;
  Serial.print("Q,"); Serial.print(imu.label); Serial.print(','); Serial.print(now);
  Serial.print(','); Serial.print(imu.x, 5);
  Serial.print(','); Serial.print(imu.y, 5);
  Serial.print(','); Serial.print(imu.z, 5);
  Serial.print(','); Serial.print(imu.w, 5);
  Serial.print(','); Serial.print(imu.accuracyRad, 5);
  Serial.print(','); Serial.println(now - imu.lastMotionMs);
}

void sample(Imu& imu) {
  if (!imu.ready) return;
  int8_t result = bhi360_get_and_process_fifo(fifoBuffer, sizeof(fifoBuffer), &imu.dev);
  if (result != BHI360_OK) {
    ++imu.errorCount;
    if (imu.errorCount <= 5 || imu.errorCount % 100 == 0) {
      Serial.print("# "); Serial.print(imu.label);
      Serial.print(" fifo_error="); Serial.println(static_cast<int>(result));
    }
  }
}

} // namespace

void SERCOM1_Handler() { busA.onService(); }
void SERCOM2_Handler() { busB.onService(); }

void setup() {
  Serial.begin(115200);
  const uint32_t start = millis();
  while (!Serial && millis() - start < 3500) delay(10);
  Serial.println("# KEVIN Dual BHI360 GameRV v0.1 EXPERIMENTAL");
  Serial.println("# Sensor A1=CHEST, Sensor B1=HEAD, both at I2C 0x29");
  if (!pinsMatch(SDA_A, PORTA, 16) || !pinsMatch(SCL_A, PORTA, 17) ||
      !pinsMatch(SDA_B, PORTA, 12) || !pinsMatch(SCL_B, PORTA, 13)) {
    Serial.println("# FATAL PINMAP_MISMATCH; stopping to protect hardware");
    while (true) delay(1000);
  }
  busA.begin();
  pinPeripheral(SDA_A, PIO_SERCOM); pinPeripheral(SCL_A, PIO_SERCOM);
  busA.setClock(100000);
  busB.begin();
  pinPeripheral(SDA_B, PIO_SERCOM); pinPeripheral(SCL_B, PIO_SERCOM);
  busB.setClock(100000);

  const bool chestReady = initImu(chest);
  const bool headReady = initImu(head);
  if (!chestReady || !headReady) {
    Serial.println("# INIT_INCOMPLETE: check errors above; returning to identification firmware may be necessary");
  }
  Serial.println("# CSV: Q,LOCATION,host_ms,qx,qy,qz,qw,accuracy_rad,age_ms");
}

void loop() {
  static uint32_t lastPoll = 0, lastPrint = 0;
  const uint32_t now = millis();
  if (static_cast<uint32_t>(now - lastPoll) >= SAMPLE_INTERVAL_MS) {
    lastPoll = now;
    sample(chest);
    sample(head);
  }
  if (static_cast<uint32_t>(now - lastPrint) >= PRINT_INTERVAL_MS) {
    lastPrint = now;
    printSample(chest, now);
    printSample(head, now);
  }
}
