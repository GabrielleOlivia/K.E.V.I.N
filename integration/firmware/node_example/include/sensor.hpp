#pragma once
#include <stdint.h>
#include <math.h>

namespace kevin {
struct Sample {
    const char* sensor_id;
    const char* measurement;
    const char* unit;
    uint32_t t_ms;
    float values[4];
    uint8_t count;
    bool valid;
    const char* calibration;
    const char* error;
};
// poll() must return promptly. true means one sample (valid OR invalid) is ready.
// Acquisition timestamps belong to the driver, not to the serial publisher.
class SensorDriver {
public:
    virtual ~SensorDriver() {}
    virtual bool begin() = 0;
    virtual bool poll(uint32_t now_ms, Sample& sample) = 0;
    virtual bool requestCalibration() = 0;
};

class MockImu : public SensorDriver {
    uint32_t last_ = 0;
    bool started_ = false;
public:
    bool begin() override { started_ = true; return true; }
    bool requestCalibration() override { return started_; }
    bool poll(uint32_t now, Sample& s) override {
        if (!started_ || static_cast<uint32_t>(now-last_) < 100) return false;
        last_ = now;
        float a = 0.15f*sinf(static_cast<float>(now % 100000)/1000.0f);
        s = {"head_imu", "orientation", "quaternion_wxyz", now,
             {cosf(a),0,sinf(a),0}, 4, true, "simulated", nullptr};
        return true;
    }
};

// A real module with unknown hardware must report unavailability, never fabricate
// a register map or return a plausible zero orientation as a successful reading.
class UnavailableImu : public SensorDriver {
    uint32_t last_ = 0;
public:
    bool begin() override { return false; }
    bool requestCalibration() override { return false; }
    bool poll(uint32_t now, Sample& s) override {
        if (static_cast<uint32_t>(now-last_) < 1000) return false;
        last_ = now;
        s = {"head_imu", "orientation", "quaternion_wxyz", now,
             {0,0,0,0},4,false,"unknown","HARDWARE_NOT_VALIDATED"};
        return true;
    }
};
}
