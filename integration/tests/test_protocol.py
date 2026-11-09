import json
import random
import unittest
from dataclasses import replace
from kevin.protocol import *
from kevin.registry import load_registry, SensorSpec
from tests.support import sample, hello

class ProtocolTests(unittest.TestCase):
    def test_roundtrip_all_message_types(self):
        for m in (hello(), sample(), Message(1,'heartbeat','pressure_node','a',2,200),
                  Message(1,'status','pressure_node','a',3,300),
                  Message(1,'fault','pressure_node','a',4,400,status='fault',error='ADC')):
            self.assertEqual(decode(encode(m)),m)

    def test_reject_envelope_mutations(self):
        variants={'v':[True,2,None],'seq':[True,-1,2**32,1.5],'t_ms':[True,-1,2**32],
                  'node_id':['','a b',[]],'type':['bogus',[]],'clock':['utc',None],
                  'valid':[1,'true'],'calibration':[[], 'ready'],'meta':[[],None]}
        for key,values in variants.items():
            for value in values:
                with self.subTest(key=key,value=value),self.assertRaises(ProtocolError):
                    d=sample().to_dict();d[key]=value;decode(json.dumps(d))

    def test_reject_nonfinite_bool_null_values(self):
        for val in (True,None,float('nan'),float('inf'),'42',{},[1,None,0,0]):
            with self.subTest(val=val),self.assertRaises(ProtocolError):
                encode(replace(sample(),value=val))

    def test_invalid_must_be_null(self):
        with self.assertRaises(ProtocolError): encode(replace(sample(),valid=False))
        m=replace(sample(),valid=False,value=None,status='invalid',error='READ_FAILED')
        self.assertEqual(decode(encode(m)),m)

    def test_duplicates_and_unknown_keys(self):
        with self.assertRaises(ProtocolError): decode('{"v":1,"v":1}')
        d=sample().to_dict();d['junk']=0
        with self.assertRaises(ProtocolError): decode(json.dumps(d))

    def test_bad_encoding_depth_size(self):
        for bad in (b'\xff',b'x'*1025, b'[]', b'{', b'['*5000):
            with self.assertRaises(ProtocolError): decode(bad)
        d=sample().to_dict();d['meta']={'a':{'b':{'c':{'d':{'e':{'f':1}}}}}}
        with self.assertRaises(ProtocolError): encode(d)

    def test_random_bytes_safe(self):
        rng=random.Random(4)
        for _ in range(500):
            raw=bytes(rng.randrange(256) for _ in range(rng.randrange(1,1100)))
            try: decode(raw)
            except ProtocolError: pass

    def test_engineering_bounds_and_quaternion(self):
        specs={s.sensor_id:s for s in load_registry()}
        specs['pressure'].check(sample(value=-65535))
        with self.assertRaises(ProtocolError): specs['pressure'].check(sample(value=-65536))
        q=sample(sensor='head_imu',node='head_node',value=[1,0,0,0])
        specs['head_imu'].check(q)
        for value in ([0,0,0,0],[1,0,0],0,[2,0,0,0]):
            with self.assertRaises(ProtocolError): specs['head_imu'].check(replace(q,value=value))

    def test_registry_rejects_bad_timeouts(self):
        with self.assertRaises(ValueError): SensorSpec('x','n','m','N',stale_s=5,disconnect_s=1)

    def test_sequence_modulo(self):
        self.assertTrue(newer_u32(0,0xFFFFFFFF))
        self.assertFalse(newer_u32(1,1));self.assertFalse(newer_u32(0,1))
        self.assertFalse(newer_u32(0x80000000,0))
