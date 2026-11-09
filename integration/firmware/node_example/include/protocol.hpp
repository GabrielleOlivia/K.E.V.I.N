#pragma once
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "sensor.hpp"

namespace kevin {
struct Envelope {
    const char* type;
    const char* node;
    const char* boot;
    uint32_t seq;
    uint32_t t_ms;
    bool simulated;
};
inline bool identifier(const char* s) {
    if (!s || !*s || strlen(s)>64) return false;
    for (;*s;++s) {
        if (!((*s>='a'&&*s<='z')||(*s>='A'&&*s<='Z')||(*s>='0'&&*s<='9')||
              *s=='_'||*s=='-'||*s=='.'||*s==':')) return false;
    }
    return true;
}
// Allocation-free, bounded JSON serializer for hello/heartbeat/measurement.
// Node faults can be sent as invalid measurements; node-wide status/fault messages
// remain supported by the host wire contract, but aren't needed by this mock.
inline bool encode(const Envelope& e, const Sample* s, char* output, size_t capacity) {
    if (!output || capacity==0) return false;
    output[0]=0;
    if (!identifier(e.node)||!identifier(e.boot)||!identifier(e.type)) return false;
    char payload[384];
    if (s) {
        if (strcmp(e.type,"measurement")!=0 || !identifier(s->sensor_id)||!identifier(s->measurement)||
            !identifier(s->unit)||!identifier(s->calibration)|| (s->error && !identifier(s->error))) return false;
        if (!(s->count==1 || s->count==4)) return false;
        for (uint8_t i=0;i<s->count;++i) if (s->valid && !isfinite(s->values[i])) return false;
        if (!s->valid && !s->error) return false;
        char values[128];
        int n;
        if (!s->valid) n=snprintf(values,sizeof(values),"null");
        else if (s->count==1) n=snprintf(values,sizeof(values),"%.6f",static_cast<double>(s->values[0]));
        else n=snprintf(values,sizeof(values),"[%.6f,%.6f,%.6f,%.6f]",static_cast<double>(s->values[0]),
                        static_cast<double>(s->values[1]),static_cast<double>(s->values[2]),static_cast<double>(s->values[3]));
        if (n<0 || static_cast<size_t>(n)>=sizeof(values)) return false;
        char err[70];
        if (s->error) snprintf(err,sizeof(err),"\"%s\"",s->error); else snprintf(err,sizeof(err),"null");
        n=snprintf(payload,sizeof(payload),",\"sensor_id\":\"%s\",\"measurement\":\"%s\",\"unit\":\"%s\",\"value\":%s,\"valid\":%s,\"status\":\"%s\",\"calibration\":\"%s\",\"error\":%s",
                   s->sensor_id,s->measurement,s->unit,values,s->valid?"true":"false",s->valid?"ok":"invalid",s->calibration,err);
        if (n<0 || static_cast<size_t>(n)>=sizeof(payload)) return false;
    } else {
        if (strcmp(e.type,"hello") && strcmp(e.type,"heartbeat")) return false;
        payload[0]=0;
    }
    int n=snprintf(output,capacity,"{\"v\":1,\"type\":\"%s\",\"node_id\":\"%s\",\"boot_id\":\"%s\",\"seq\":%lu,\"t_ms\":%lu,\"clock\":\"uptime_ms\",\"meta\":{\"simulated\":%s}%s}\n",
                   e.type,e.node,e.boot,static_cast<unsigned long>(e.seq),
                   static_cast<unsigned long>(s?s->t_ms:e.t_ms),e.simulated?"true":"false",payload);
    if (n<0 || static_cast<size_t>(n)>=capacity || n>1025) { output[0]=0; return false; }
    return true;
}

class Transport {
public:
    virtual ~Transport() {}
    virtual bool send(const char* bytes, size_t size) = 0;
};
}
