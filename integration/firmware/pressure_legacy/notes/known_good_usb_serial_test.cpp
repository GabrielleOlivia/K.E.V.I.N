#include <Arduino.h>

void setup()
{
    Serial.begin(115200);

    unsigned long start = millis();
    while (!Serial && (millis() - start < 5000))
    {
    }

    Serial.println("SensorHub test starting");
}

void loop()
{
    Serial.println("SensorHub alive");
    delay(1000);
}
