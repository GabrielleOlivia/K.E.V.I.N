#include <Arduino.h>
#include "protocol.hpp"

// EXAMPLE ONLY: synthetic head orientation, no I2C/SPI or actuator pin accesses.
// Host assigns a new SESSION on each port-open/boot request; this avoids pretending
// millis() or a fixed string is a globally unique boot ID.
kevin::MockImu imu;
char boot[65] = {};
char command[96] = {};
char pendingBoot[65] = {};
size_t commandLength = 0;
bool discardCommand = false;
uint32_t sequence = 0, lastRequest = 0, lastHeartbeat = 0;
char tx[1026];
size_t txLength = 0, txOffset = 0;

class UsbTransport : public kevin::Transport {
public:
    bool send(const char* bytes, size_t length) override {
        if (txLength || length>sizeof(tx)) return false;
        memcpy(tx,bytes,length); txLength=length; txOffset=0; return true;
    }
    void poll() {
        if (!txLength || !Serial) return;
        int room=Serial.availableForWrite();
        if (room<=0) return;
        size_t amount=txLength-txOffset;
        if (amount>static_cast<size_t>(room)) amount=static_cast<size_t>(room);
        txOffset+=Serial.write(reinterpret_cast<const uint8_t*>(tx+txOffset),amount);
        if (txOffset==txLength) { txLength=0; txOffset=0; }
    }
} usb;

bool publish(const char* kind, const kevin::Sample* sample=nullptr) {
    if (txLength) return false;
    char output[1026];
    kevin::Envelope e={kind,"head_node",boot,sequence,millis(),true};
    if (!kevin::encode(e,sample,output,sizeof(output))) return false;
    if (!usb.send(output,strlen(output))) return false;
    ++sequence;
    return true;
}
void setup() { Serial.begin(115200); imu.begin(); }
void loop() {
    usb.poll();
    while (Serial.available()) {
        char c=static_cast<char>(Serial.read());
        if (c=='\n') {
            command[commandLength]=0;
            if (!discardCommand && !strncmp(command,"SESSION ",8) && kevin::identifier(command+8)) {
                // Queue the request even while an old line is being transmitted.
                strncpy(pendingBoot,command+8,sizeof(pendingBoot)-1);
                pendingBoot[sizeof(pendingBoot)-1]=0;
            }
            commandLength=0; discardCommand=false;
        } else if (c!='\r' && !discardCommand) {
            if (commandLength<sizeof(command)-1) command[commandLength++]=c;
            else { commandLength=0; discardCommand=true; }
        }
    }
    if (pendingBoot[0] && !txLength) {
        strcpy(boot,pendingBoot); pendingBoot[0]=0;
        sequence=0; publish("hello");
    }
    uint32_t now=millis();
    if (!boot[0]) {
        if (static_cast<uint32_t>(now-lastRequest)>=1000 && !txLength) {
            lastRequest=now;
            const char request[]="# SESSION_REQUIRED\n";
            usb.send(request,sizeof(request)-1);
        }
        return;
    }
    if (txLength) return;
    kevin::Sample sample;
    if (static_cast<uint32_t>(now-lastHeartbeat)>=1000) {
        if (publish("heartbeat")) lastHeartbeat=now;
    } else if (imu.poll(now,sample)) {
        publish("measurement",&sample);
    }
}
