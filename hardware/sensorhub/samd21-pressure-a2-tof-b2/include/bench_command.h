#pragma once
#include <Arduino.h>
#include <ctype.h>

// Execute one character followed by Enter. A pasted word must not arm a test.
inline char readBenchCommand() {
  static char pending = 0;
  while (Serial.available()) {
    const int byte = Serial.read();
    if (byte == '\r' || byte == '\n') {
      const char command = pending;
      pending = 0;
      if (command) return command;
    } else if (byte >= 0) {
      pending = pending ? '?' : static_cast<char>(tolower(byte));
    }
  }
  return 0;
}
