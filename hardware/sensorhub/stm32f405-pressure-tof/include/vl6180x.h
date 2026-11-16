// Adapted from OlympusSixtems/KEVIN (team repository), branch feature/stm32f405-vl6180x-tof-probe
// Original file: firmware/tof_probe_f405/include/vl6180x.h
// Git blob: 8c69ce9b277c1372c0b8da27ba6f803a29d380e8

// Minimal VL6180X access over an Arduino TwoWire bus (diagnostic use only).
//
// Register map and the mandatory private settings follow ST AN4545
// ("VL6180X basic ranging application note") and the VL6180X datasheet
// (DocID026171). 7-bit address 0x29, 16-bit register index, big-endian.
#pragma once

#include <Arduino.h>
#include <Wire.h>

namespace vl6180x {

const uint8_t ADDRESS = 0x29;
const uint8_t EXPECTED_MODEL_ID = 0xB4;

// Public registers used here.
const uint16_t IDENTIFICATION__MODEL_ID = 0x000;
const uint16_t IDENTIFICATION__MODEL_REV_MAJOR = 0x001;
const uint16_t IDENTIFICATION__MODEL_REV_MINOR = 0x002;
const uint16_t IDENTIFICATION__MODULE_REV_MAJOR = 0x003;
const uint16_t IDENTIFICATION__MODULE_REV_MINOR = 0x004;
const uint16_t SYSTEM__INTERRUPT_CONFIG_GPIO = 0x014;
const uint16_t SYSTEM__INTERRUPT_CLEAR = 0x015;
const uint16_t SYSTEM__FRESH_OUT_OF_RESET = 0x016;
const uint16_t SYSRANGE__START = 0x018;
const uint16_t RESULT__RANGE_STATUS = 0x04D;
const uint16_t RESULT__INTERRUPT_STATUS_GPIO = 0x04F;
const uint16_t RESULT__RANGE_VAL = 0x062;

struct Identity {
    uint8_t modelId = 0;
    uint8_t modelRevMajor = 0;
    uint8_t modelRevMinor = 0;
    uint8_t moduleRevMajor = 0;
    uint8_t moduleRevMinor = 0;
    uint8_t freshOutOfReset = 0;
};

struct Range {
    uint8_t mm = 0;          // raw RESULT__RANGE_VAL (0..255 mm), not calibrated
    uint8_t errorCode = 0;   // RESULT__RANGE_STATUS[7:4]; 0 = no error
};

class Device {
public:
    explicit Device(TwoWire &bus, uint8_t address = ADDRESS) : bus_(bus), address_(address) {}

    // true if the device acknowledges its address.
    bool present() {
        bus_.beginTransmission(address_);
        return bus_.endTransmission() == 0;
    }

    bool read8(uint16_t reg, uint8_t &value) {
        bus_.beginTransmission(address_);
        bus_.write((uint8_t)(reg >> 8));
        bus_.write((uint8_t)(reg & 0xFF));
        if (bus_.endTransmission() != 0) {
            return false;
        }
        if (bus_.requestFrom(address_, (uint8_t)1) != 1) {
            while (bus_.available()) {
                bus_.read();
            }
            return false;
        }
        value = (uint8_t)bus_.read();
        return true;
    }

    bool write8(uint16_t reg, uint8_t value) {
        bus_.beginTransmission(address_);
        bus_.write((uint8_t)(reg >> 8));
        bus_.write((uint8_t)(reg & 0xFF));
        bus_.write(value);
        return bus_.endTransmission() == 0;
    }

    bool readIdentity(Identity &id) {
        return read8(IDENTIFICATION__MODEL_ID, id.modelId) &&
               read8(IDENTIFICATION__MODEL_REV_MAJOR, id.modelRevMajor) &&
               read8(IDENTIFICATION__MODEL_REV_MINOR, id.modelRevMinor) &&
               read8(IDENTIFICATION__MODULE_REV_MAJOR, id.moduleRevMajor) &&
               read8(IDENTIFICATION__MODULE_REV_MINOR, id.moduleRevMinor) &&
               read8(SYSTEM__FRESH_OUT_OF_RESET, id.freshOutOfReset);
    }

    // Mandatory private settings (AN4545 §"SR03 settings") plus the
    // recommended public defaults, applied once after a fresh reset.
    bool init() {
        static const uint16_t kSettings[][2] = {
            // private registers — required after every power-up
            {0x0207, 0x01}, {0x0208, 0x01}, {0x0096, 0x00}, {0x0097, 0xFD},
            {0x00E3, 0x00}, {0x00E4, 0x04}, {0x00E5, 0x02}, {0x00E6, 0x01},
            {0x00E7, 0x03}, {0x00F5, 0x02}, {0x00D9, 0x05}, {0x00DB, 0xCE},
            {0x00DC, 0x03}, {0x00DD, 0xF8}, {0x009F, 0x00}, {0x00A3, 0x3C},
            {0x00B7, 0x00}, {0x00BB, 0x3C}, {0x00B2, 0x09}, {0x00CA, 0x09},
            {0x0198, 0x01}, {0x01B0, 0x17}, {0x01AD, 0x00}, {0x00FF, 0x05},
            {0x0100, 0x05}, {0x0199, 0x05}, {0x01A6, 0x1B}, {0x01AC, 0x3E},
            {0x01A7, 0x1F}, {0x0030, 0x00},
            // recommended public settings (AN4545; cross-checked with the
            // Pololu vl6180x-arduino configureDefault())
            {0x0011, 0x10},  // SYSTEM__MODE_GPIO1: interrupt output, active low
            {0x010A, 0x30},  // READOUT__AVERAGING_SAMPLE_PERIOD
            {0x003F, 0x46},  // SYSALS__ANALOGUE_GAIN
            {0x0031, 0xFF},  // SYSRANGE__VHV_REPEAT_RATE
            {0x0040, 0x00},  // SYSALS__INTEGRATION_PERIOD, 16-bit 0x0063 (100 ms):
            {0x0041, 0x63},  //   high byte, then low byte
            {0x002E, 0x01},  // SYSRANGE__VHV_RECALIBRATE
            {0x001B, 0x09},  // SYSRANGE__INTERMEASUREMENT_PERIOD (100 ms)
            {0x003E, 0x31},  // SYSALS__INTERMEASUREMENT_PERIOD (500 ms)
            {0x0014, 0x24},  // SYSTEM__INTERRUPT_CONFIG_GPIO: new-sample-ready
            {0x001C, 0x31},  // SYSRANGE__MAX_CONVERGENCE_TIME (49 ms)
            {0x02A3, 0x00},  // INTERLEAVED_MODE__ENABLE: off
        };
        uint8_t fresh = 0;
        if (!read8(SYSTEM__FRESH_OUT_OF_RESET, fresh)) {
            return false;
        }
        if (fresh == 1) {
            for (const auto &s : kSettings) {
                if (!write8(s[0], (uint8_t)s[1])) {
                    return false;
                }
            }
            if (!write8(SYSTEM__FRESH_OUT_OF_RESET, 0x00)) {
                return false;
            }
        }
        return true;
    }

    // Single-shot range measurement. Returns false on bus error or timeout.
    bool measure(Range &out, uint32_t timeoutMs = 100) {
        uint32_t start = millis();
        uint8_t status = 0;
        // Wait for device ready (RESULT__RANGE_STATUS bit 0).
        do {
            if (!read8(RESULT__RANGE_STATUS, status)) {
                return false;
            }
            if (millis() - start > timeoutMs) {
                return false;
            }
        } while ((status & 0x01) == 0);

        if (!write8(SYSRANGE__START, 0x01)) {
            return false;
        }
        uint8_t irq = 0;
        start = millis();
        do {
            if (!read8(RESULT__INTERRUPT_STATUS_GPIO, irq)) {
                return false;
            }
            if (millis() - start > timeoutMs) {
                return false;
            }
        } while ((irq & 0x07) != 0x04);  // range: new sample ready

        uint8_t mm = 0;
        uint8_t rangeStatus = 0;
        bool ok = read8(RESULT__RANGE_VAL, mm) && read8(RESULT__RANGE_STATUS, rangeStatus);
        write8(SYSTEM__INTERRUPT_CLEAR, 0x07);
        if (!ok) {
            return false;
        }
        out.mm = mm;
        out.errorCode = rangeStatus >> 4;
        return true;
    }

private:
    TwoWire &bus_;
    uint8_t address_;
};

}  // namespace vl6180x
