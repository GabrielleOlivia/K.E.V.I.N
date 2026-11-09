"""Independent pure signal generators. Values are engineering test fixtures."""
import math


def pressure(t, rng):
    return round(450*max(0, math.sin(t*2))+rng.uniform(-4, 4)), {'candidate_count':int(t//3.14159), 'model':'synthetic excursion'}


def head(t, rng):
    a = math.radians(20*math.sin(t))/2
    return [math.cos(a), 0, math.sin(a), 0], {'frame_id':'sim_world', 'mounting_calibrated':True}


def chest(t, rng):
    a = math.radians(5*math.sin(t))/2
    return [math.cos(a), 0, math.sin(a), 0], {'frame_id':'sim_world', 'mounting_calibrated':True}


def cpr(t, rng):
    return max(0, 12*math.sin(t*10)), {}


def temperature(t, rng):
    return 35.0+0.3*math.sin(t/5), {}


def spo2(t, rng):
    return 96.0+math.sin(t/3), {}


GENERATORS = {'pressure':pressure, 'head_imu':head, 'chest_imu':chest,
              'cpr':cpr, 'temperature':temperature, 'spo2':spo2}
