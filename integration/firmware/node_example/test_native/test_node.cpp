#include <cassert>
#include <iostream>
#include <limits>
#include "protocol.hpp"
int main() {
    kevin::MockImu imu;
    kevin::Sample s;
    assert(!imu.poll(100,s));
    assert(imu.begin());
    assert(!imu.poll(99,s));
    assert(imu.poll(100,s));
    assert(s.valid && s.count==4);
    assert(fabs(s.values[0]*s.values[0]+s.values[2]*s.values[2]-1)<0.0001);
    char out[1026], tiny[8];
    kevin::Envelope e={"hello","head_node","native-test",0,0,true};
    assert(kevin::encode(e,nullptr,out,sizeof(out))); std::cout<<out;
    e.type="measurement";e.seq=1;
    assert(kevin::encode(e,&s,out,sizeof(out))); std::cout<<out;
    assert(!kevin::encode(e,&s,tiny,sizeof(tiny)) && tiny[0]==0);
    s.values[0]=std::numeric_limits<float>::quiet_NaN();
    assert(!kevin::encode(e,&s,out,sizeof(out)));
    kevin::UnavailableImu missing;
    assert(!missing.begin());assert(missing.poll(1000,s));assert(!s.valid);
    e.seq=2;assert(kevin::encode(e,&s,out,sizeof(out)));std::cout<<out;
    assert(!kevin::identifier("bad\"id"));
    assert(imu.poll(0xFFFFFFF0u,s));assert(imu.poll(100u,s));
    return 0;
}
