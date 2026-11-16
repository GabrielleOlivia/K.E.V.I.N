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
#include "bhi360/Bosch_Shuttle3_BHI360_bsxsam_lite.fw.h"

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
// Diagnostic experiment: allow the BHI360 command-channel consumer to
// catch up between consecutive 28-byte chunks. 28 is word-aligned (4 bytes).
constexpr uint32_t FW_UPLOAD_PACING_US = 1000;

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
  // Trace most recent low-level I2C failure during firmware transfer.
  uint8_t lastWireStatus;
  uint8_t lastWireStage; // 1=write address/register, 2=short read, 3=TX overflow, 4=TX NACK
  uint8_t lastWireRegister;
  uint32_t lastWireLength;
  bool trackingUpload;
  uint32_t successfulUploadWrites;
  uint32_t successfulUploadBytes;
  uint32_t failedAtWrite;
  uint32_t failedAtByte;
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
// Trace only the last failed transfer; do not print inside I2C callbacks.
void markI2cFailure(Imu& imu, uint8_t stage, uint8_t status, uint8_t reg, uint32_t len) {
  imu.lastWireStage = stage;
  imu.lastWireStatus = status;
  imu.lastWireRegister = reg;
  imu.lastWireLength = len;
}

int8_t boschRead(uint8_t reg, uint8_t *data, uint32_t len, void *context) {
  auto* imu = static_cast<Imu*>(context);
  if (!imu) return -1;
  imu->lastWireStage = 0;
  if (!data || !len || len > 28) {
    markI2cFailure(*imu, 5, 0, reg, len);
    return -1;
  }
  TwoWire& wire = *imu->wire;
  wire.beginTransmission(SENSOR_ADDRESS);
  wire.write(reg);
  uint8_t status = wire.endTransmission(false);
  if (status != 0) {
    markI2cFailure(*imu, 1, status, reg, len);
    return -1;
  }
  const uint8_t requested = static_cast<uint8_t>(len);
  uint8_t received = wire.requestFrom(SENSOR_ADDRESS, requested, static_cast<uint8_t>(true));
  if (received != requested) {
    markI2cFailure(*imu, 2, received, reg, len);
    while (wire.available()) wire.read();
    return -1;
  }
  for (uint32_t i = 0; i < len; ++i) data[i] = static_cast<uint8_t>(wire.read());
  return 0;
}

int8_t boschWrite(uint8_t reg, const uint8_t *data, uint32_t len, void *context) {
  auto* imu = static_cast<Imu*>(context);
  if (!imu) return -1;
  imu->lastWireStage = 0;
  if ((len && !data) || len > 28) {
    markI2cFailure(*imu, 5, 0, reg, len);
    return -1;
  }
  TwoWire& wire = *imu->wire;
  wire.beginTransmission(SENSOR_ADDRESS);
  wire.write(reg);
  if (len && wire.write(data, len) != len) {
    markI2cFailure(*imu, 3, 0, reg, len);
    wire.endTransmission(true);
    return -1;
  }
  const uint8_t status = wire.endTransmission(true);
  if (status != 0) {
    if (imu->trackingUpload && reg == BHI360_REG_CHAN_CMD) {
      imu->failedAtWrite = imu->successfulUploadWrites + 1;
      imu->failedAtByte = imu->successfulUploadBytes;
    }
    markI2cFailure(*imu, 4, status, reg, len);
    return -1;
  }
  if (imu->trackingUpload && reg == BHI360_REG_CHAN_CMD) {
    ++imu->successfulUploadWrites;
    imu->successfulUploadBytes += len;
    // Intentional pacing, ONLY during the manually requested firmware upload.
    delayMicroseconds(FW_UPLOAD_PACING_US);
  }
  return 0;
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

// Post-failure snapshot: status bits help distinguish bus failures from
// firmware verification/boot failure. No config writes or retries here.
void printDiagnostics(Imu& imu, const char* phase) {
  Serial.print("# "); Serial.print(imu.label);
  Serial.print(" DIAG phase="); Serial.println(phase);
  Serial.print("# "); Serial.print(imu.label);
  Serial.print(" I2C stage="); Serial.print(imu.lastWireStage);
  Serial.print(" status="); Serial.print(imu.lastWireStatus);
  Serial.print(" reg=0x"); Serial.print(imu.lastWireRegister, HEX);
  Serial.print(" length="); Serial.print(imu.lastWireLength);
  Serial.print(" api_intf_result="); Serial.println(static_cast<int>(imu.dev.hif.intf_rslt));

  // The following reads are observational only; they do not reset the BHI360.
  uint8_t boot = 0;
  int8_t result = bhi360_get_boot_status(&boot, &imu.dev);
  Serial.print("# "); Serial.print(imu.label);
  Serial.print(" boot_status_read_result="); Serial.print(static_cast<int>(result));
  if (result == BHI360_OK) {
    Serial.print(" boot=0x"); Serial.print(boot, HEX);
    Serial.print(" host_ready="); Serial.print((boot & BHI360_BST_HOST_INTERFACE_READY) != 0);
    Serial.print(" verify_done="); Serial.print((boot & BHI360_BST_HOST_FW_VERIFY_DONE) != 0);
    Serial.print(" verify_error="); Serial.print((boot & BHI360_BST_HOST_FW_VERIFY_ERROR) != 0);
  }
  Serial.println();

  uint8_t sensorError = 0;
  result = bhi360_get_error_value(&sensorError, &imu.dev);
  Serial.print("# "); Serial.print(imu.label);
  Serial.print(" sensor_error_read_result="); Serial.print(static_cast<int>(result));
  if (result == BHI360_OK) {
    Serial.print(" sensor_error=0x"); Serial.print(sensorError, HEX);
  }
  Serial.println();

  uint8_t debugState = 0;
  result = bhi360_get_regs(BHI360_REG_DEBUG_STATE, &debugState, 1, &imu.dev);
  Serial.print("# "); Serial.print(imu.label);
  Serial.print(" debug_state_read_result="); Serial.print(static_cast<int>(result));
  if (result == BHI360_OK) {
    Serial.print(" debug_state=0x"); Serial.print(debugState, HEX);
  }
  Serial.println();

  uint8_t debugValue = 0;
  result = bhi360_get_regs(BHI360_REG_DEBUG_VALUE, &debugValue, 1, &imu.dev);
  Serial.print("# "); Serial.print(imu.label);
  Serial.print(" debug_value_read_result="); Serial.print(static_cast<int>(result));
  if (result == BHI360_OK) {
    Serial.print(" debug_value=0x"); Serial.print(debugValue, HEX);
  }
  Serial.println();
}

// Read-only preflight. Does not soft-reset, upload, boot, or configure fusion.
void preflight(Imu& imu) {
  Serial.print("# "); Serial.print(imu.label);
  Serial.println(" PREFLIGHT_BEGIN (reads only)");

  uint8_t fuserId = 0;
  if (!readChipId(*imu.wire, fuserId)) {
    Serial.print("# "); Serial.print(imu.label);
    Serial.println(" FUSER2_ID_READ_FAILED");
    return;
  }
  Serial.print("# "); Serial.print(imu.label);
  Serial.print(" fuser2_id=0x"); Serial.println(fuserId, HEX);
  if (fuserId != FUSER2_ID_EXPECTED) {
    Serial.print("# "); Serial.print(imu.label);
    Serial.println(" WRONG_FUSER2_ID; no initialization allowed");
    return;
  }
  const int8_t api = bhi360_init(BHI360_I2C_INTERFACE, boschRead, boschWrite,
                                 boschDelay, 28, &imu, &imu.dev);
  Serial.print("# "); Serial.print(imu.label);
  Serial.print(" api_bind_result="); Serial.println(static_cast<int>(api));
  if (api != BHI360_OK) return;

  uint8_t chip = 0;
  int8_t status = bhi360_get_chip_id(&chip, &imu.dev);
  Serial.print("# "); Serial.print(imu.label);
  Serial.print(" chip_id_result="); Serial.print(static_cast<int>(status));
  if (status == BHI360_OK) {
    Serial.print(" chip_id=0x"); Serial.print(chip, HEX);
    Serial.print(" expected=0x"); Serial.print(BHI360_CHIP_ID, HEX);
    Serial.print(" match="); Serial.print(chip == BHI360_CHIP_ID ? "yes" : "no");
  }
  Serial.println();

  uint8_t revision = 0;
  status = bhi360_get_revision_id(&revision, &imu.dev);
  Serial.print("# "); Serial.print(imu.label);
  Serial.print(" revision_result="); Serial.print(static_cast<int>(status));
  if (status == BHI360_OK) {
    Serial.print(" rev=0x"); Serial.print(revision, HEX);
  }
  Serial.println();

  uint16_t rom = 0;
  status = bhi360_get_rom_version(&rom, &imu.dev);
  Serial.print("# "); Serial.print(imu.label);
  Serial.print(" rom_version_result="); Serial.print(static_cast<int>(status));
  if (status == BHI360_OK) {
    Serial.print(" rom="); Serial.print(rom);
    Serial.print(" (0x"); Serial.print(rom, HEX); Serial.print(")");
  }
  Serial.println();

  uint8_t boot = 0;
  status = bhi360_get_boot_status(&boot, &imu.dev);
  Serial.print("# "); Serial.print(imu.label);
  Serial.print(" boot_status_result="); Serial.print(static_cast<int>(status));
  if (status == BHI360_OK) {
    Serial.print(" boot=0x"); Serial.print(boot, HEX);
  }
  Serial.println();

  uint8_t errorValue = 0;
  status = bhi360_get_error_value(&errorValue, &imu.dev);
  Serial.print("# "); Serial.print(imu.label);
  Serial.print(" error_value_result="); Serial.print(static_cast<int>(status));
  if (status == BHI360_OK) {
    Serial.print(" error=0x"); Serial.print(errorValue, HEX);
  }
  Serial.println();

  uint8_t aux = 0;
  status = bhi360_get_regs(BHI360_REG_ERROR_AUX, &aux, 1, &imu.dev);
  Serial.print("# "); Serial.print(imu.label);
  Serial.print(" error_aux_result="); Serial.print(static_cast<int>(status));
  if (status == BHI360_OK) {
    Serial.print(" error_aux=0x"); Serial.print(aux, HEX);
  }
  Serial.println();

  Serial.print("# "); Serial.print(imu.label);
  Serial.println(" PREFLIGHT_END");
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
  // Deliberately scope pacing and byte counting to the firmware upload.
  imu.successfulUploadWrites = 0;
  imu.successfulUploadBytes = 0;
  imu.failedAtWrite = 0;
  imu.failedAtByte = 0;
  imu.trackingUpload = true;
  const uint32_t uploadStartMs = millis();
  const int8_t uploadResult = bhi360_upload_firmware_to_ram(
      bhi360_firmware_image, sizeof(bhi360_firmware_image), &imu.dev);
  const uint32_t uploadElapsedMs = millis() - uploadStartMs;
  imu.trackingUpload = false;
  Serial.print("# "); Serial.print(imu.label);
  Serial.print(" upload_progress accepted_writes="); Serial.print(imu.successfulUploadWrites);
  Serial.print(" accepted_channel_bytes="); Serial.print(imu.successfulUploadBytes);
  Serial.print(" failed_write="); Serial.print(imu.failedAtWrite);
  Serial.print(" failed_after_bytes="); Serial.print(imu.failedAtByte);
  Serial.print(" elapsed_ms="); Serial.println(uploadElapsedMs);
  if (!checked("firmware_upload", uploadResult, imu)) {
    printDiagnostics(imu, "firmware_upload_failed");
    return false;
  }
  // Always show verification status after transfer, before asking for boot.
  printDiagnostics(imu, "firmware_uploaded_before_boot");
  const int8_t bootResult = bhi360_boot_from_ram(&imu.dev);
  if (!checked("boot_from_ram", bootResult, imu)) {
    printDiagnostics(imu, "boot_from_ram_failed");
    return false;
  }
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
  Serial.println("# KEVIN Dual BHI360 GameRV v0.5 PACED-TRANSFER DIAGNOSTIC");
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

  // Previous trial had fatal sensor errors (0x11 / 0x1B).
  // Never issue firmware commands automatically when MCU is power-cycled or reset.
  preflight(chest);
  preflight(head);
  Serial.println("# Commands: p=read-only preflight; c=test CHEST once; b=test HEAD once; h=help");
  Serial.println("# At startup no firmware is uploaded. Review log before typing c or b.");
}

void loop() {
  static uint32_t lastPoll = 0, lastPrint = 0;
  static bool attemptedChest = false;
  static bool attemptedHead = false;
  while (Serial.available()) {
    const char c = static_cast<char>(Serial.read());
    if (c == 'p' || c == 'P') {
      preflight(chest);
      preflight(head);
    } else if (c == 'h' || c == 'H') {
      Serial.println("# p=preflight reads; c=one CHEST upload/boot; b=one HEAD upload/boot; h=help");
    } else if (c == 'c' || c == 'C') {
      if (attemptedChest) {
        Serial.println("# CHEST upload already attempted this MCU session. Power-cycle before repeating.");
      } else {
        attemptedChest = true;
        Serial.println("# MANUAL_LITE_CHEST_BEGIN (HEAD is left untouched)");
        const bool ready = initImu(chest);
        Serial.print("# MANUAL_LITE_CHEST_END ready=");
        Serial.println(ready ? "1" : "0");
        if (ready) Serial.println("# CSV: Q,LOCATION,host_ms,qx,qy,qz,qw,accuracy_rad,age_ms");
      }
    } else if (c == 'b' || c == 'B') {
      if (attemptedHead) {
        Serial.println("# HEAD upload already attempted this MCU session. Power-cycle before repeating.");
      } else {
        attemptedHead = true;
        Serial.println("# MANUAL_LITE_HEAD_BEGIN (CHEST is left untouched)");
        const bool ready = initImu(head);
        Serial.print("# MANUAL_LITE_HEAD_END ready=");
        Serial.println(ready ? "1" : "0");
        if (ready) Serial.println("# CSV: Q,LOCATION,host_ms,qx,qy,qz,qw,accuracy_rad,age_ms");
      }
    } else if (c == 'u' || c == 'U') {
      Serial.println("# command u disabled; use c or b for one sensor at a time.");
    }
  }
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
