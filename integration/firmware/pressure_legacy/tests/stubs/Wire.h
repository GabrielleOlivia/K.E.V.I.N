#pragma once

#include <cstdint>
#include <deque>
#include <stdexcept>

struct TestSercom {};
extern TestSercom sercom1;

struct TestConversion
{
    int16_t raw;
    uint8_t status;
    uint8_t byteCount;
    uint8_t writeError;
    TestConversion(int16_t value, uint8_t config = 0x08,
                   uint8_t bytes = 3, uint8_t error = 0)
        : raw(value), status(config), byteCount(bytes), writeError(error) {}
};

class TwoWire
{
public:
    std::deque<TestConversion> conversions;
    std::deque<uint8_t> response;
    TestConversion current{0};
    TwoWire(TestSercom *, int, int) {}
    void begin() {}
    void onService() {}
    void setClock(unsigned long) {}
    void beginTransmission(uint8_t)
    {
        if (conversions.empty()) throw std::runtime_error("Unexpected ADC read in test");
        current = conversions.front();
        conversions.pop_front();
    }
    void write(uint8_t) {}
    uint8_t endTransmission() { return current.writeError; }
    uint8_t requestFrom(uint8_t, uint8_t)
    {
        response.clear();
        const uint16_t value = static_cast<uint16_t>(current.raw);
        if (current.byteCount > 0) response.push_back(static_cast<uint8_t>(value >> 8));
        if (current.byteCount > 1) response.push_back(static_cast<uint8_t>(value & 0xFF));
        if (current.byteCount > 2) response.push_back(current.status);
        return current.byteCount;
    }
    int available() const { return static_cast<int>(response.size()); }
    int read()
    {
        if (response.empty()) throw std::runtime_error("Read past ADC response in test");
        const int value = response.front();
        response.pop_front();
        return value;
    }
};
