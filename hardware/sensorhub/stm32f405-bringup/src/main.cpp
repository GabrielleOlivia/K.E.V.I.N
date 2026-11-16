// K.E.V.I.N. / STM32F405RG MicroMod SensorHub USB-only bring-up.
// Reference carrier: RobotPatient SensorHub MicroMod Carrier v1.1.0b.
// NOT a BHI360 firmware uploader, ToF driver, or clinical monitor.
//
// IMPORTANT: No I2C peripheral is started and no sensor rail GPIO is
// driven here. This source is safe to BUILD offline. Installing it
// on a live board would still ERASE the existing application firmware.
// Make a verified backup / obtain team approval BEFORE any upload.

#include <Arduino.h>

namespace {
constexpr uint32_t BAUD = 115200;
constexpr uint32_t HEARTBEAT_MS = 2000;
uint32_t lastHeartbeat = 0;
}

void setup() {
    Serial.begin(BAUD);
    const uint32_t started = millis();
    while (!Serial && static_cast<uint32_t>(millis() - started) < 3500) {
        delay(10);
    }
    Serial.println("# KEVIN STM32F405 MicroMod USB-only bringup v0.1");
    Serial.println("# No sensor rails enabled; no I2C communication; no firmware uploads to sensors.");
    Serial.println("# STM32 application start confirmed if you can read this message after approved flash.");
    lastHeartbeat = millis();
}

void loop() {
    const uint32_t now = millis();
    if (static_cast<uint32_t>(now - lastHeartbeat) >= HEARTBEAT_MS) {
        lastHeartbeat = now;
        Serial.print("# HEARTBEAT t_ms=");
        Serial.println(now);
    }
}
