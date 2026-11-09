#pragma once

// Host-only Arduino substitutes. These do not model SAMD21 USB or peripherals.
#include <cstdint>
#include <deque>
#include <sstream>
#include <string>

extern uint32_t testMillis;
inline unsigned long millis() { return testMillis; }
inline void delay(unsigned long ms) { testMillis += static_cast<uint32_t>(ms); }

struct TestSerial
{
    std::ostringstream output;
    std::deque<char> input;
    void begin(unsigned long) {}
    explicit operator bool() const { return true; }
    int available() const { return static_cast<int>(input.size()); }
    int read()
    {
        if (input.empty()) return -1;
        const char value = input.front();
        input.pop_front();
        return value;
    }
    template <typename T> void print(const T &value) { output << value; }
    template <typename T> void println(const T &value) { output << value << '\n'; }
    void println() { output << '\n'; }
};
extern TestSerial Serial;
