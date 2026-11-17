// Separate test image. Only PA16 and PA17 are selected, by physical port bit.
// External, verified 3.3 V pull-ups supply HIGH. Peripherals stay disconnected.
#include <Arduino.h>
#include "bench_command.h"

#if !defined(__SAMD21G18A__)
#error A2 reachability requires the SAMD21G18A SensorHub target
#endif

namespace {
constexpr uint32_t kSda = 1ul << 16;
constexpr uint32_t kScl = 1ul << 17;
constexpr uint32_t kLines = kSda | kScl;
PortGroup &gpio = PORT->Group[0];
bool stopped = false;

void help() {
  Serial.println("# GPIO A2 ONLY v1: d=PA16 SDA, k=PA17 SCL, h=help; press Enter");
  Serial.println("# One 3 s LOW pulse. Check both released lines with the meter first.");
}

void stop(const char *reason) {
  gpio.DIRCLR.reg = kLines;
  stopped = true;
  Serial.print("# STOP GPIO ");
  Serial.println(reason);
}

void pulse(uint32_t mask) {
  if (stopped) {
    Serial.println("# STOP GPIO latched; inspect unpowered and restart");
    return;
  }
  if ((gpio.IN.reg & kLines) != kLines) {
    stop("idle_line_low");
    return;
  }
  Serial.println(mask == kSda ? "# GPIO PA16/SDA LOW 3s" : "# GPIO PA17/SCL LOW 3s");
  gpio.OUTCLR.reg = mask;  // preload a zero before enabling the output driver
  gpio.DIRSET.reg = mask;
  delayMicroseconds(50);
  if ((gpio.IN.reg & kLines) != (kLines ^ mask)) {
    stop("unexpected_level_during_pulse");
    return;
  }
  delay(3000);             // no USB writes while driving a line
  gpio.DIRCLR.reg = mask;  // high impedance; the latch stays zero
  delay(2);
  if ((gpio.IN.reg & kLines) != kLines) {
    stop("line_did_not_release");
    return;
  }
  Serial.println("# GPIO RELEASED both inputs; verify at the module");
}
} // namespace

void setup() {
  gpio.DIRCLR.reg = kLines;
  gpio.OUTCLR.reg = kLines;
  // GPIO input enable only: PMUXEN=0, PULLEN=0 for each pin.
  gpio.PINCFG[16].reg = PORT_PINCFG_INEN;
  gpio.PINCFG[17].reg = PORT_PINCFG_INEN;
  Serial.begin(115200);
  const uint32_t started = millis();
  while (!Serial && millis() - started < 4000) delay(10);
  help();
}

void loop() {
  const char c = readBenchCommand();
  if (c == 'd') pulse(kSda);
  else if (c == 'k') pulse(kScl);
  else if (c) help();
}
