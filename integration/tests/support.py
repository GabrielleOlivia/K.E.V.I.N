from dataclasses import replace
from kevin.protocol import Message
from kevin.manager import SensorManager
from kevin.registry import load_registry

class Clock:
    def __init__(self): self.t=100.0
    def __call__(self): return self.t
    def advance(self, dt): self.t+=dt

def hello(node='pressure_node',boot='a',seq=0,t=0,**kwargs):
    return Message(1,'hello',node,boot,seq,t,**kwargs)

def sample(seq=1,t=100,value=42,node='pressure_node',sensor='pressure',boot='a',**kwargs):
    spec=next(s for s in load_registry() if s.sensor_id==sensor)
    return Message(1,'measurement',node,boot,seq,t,sensor_id=sensor,measurement=spec.measurement,
                   value=value,unit=spec.unit,valid=True,calibration='calibrated',**kwargs)

def setup_manager():
    clock=Clock();m=SensorManager(load_registry(),clock)
    assert m.accept(hello(),'wire')
    return clock,m
