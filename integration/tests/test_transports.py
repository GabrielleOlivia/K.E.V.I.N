import threading
import unittest
from kevin.transports.framing import LineFramer
from kevin.transports.can import fragment, Reassembler
from kevin.transports.serial_source import SerialSource
from kevin.protocol import encode, ProtocolError
from kevin.service import IntegrationService
from tests.support import *

class FramingTests(unittest.TestCase):
    def test_partial_and_multiple_lines(self):
        f=LineFramer();self.assertEqual(f.feed(b'abc'),[])
        self.assertEqual(f.feed(b'\r\ndef\npart'),[b'abc',b'def'])
        self.assertEqual(f.feed(b'ial\n'),[b'partial'])
    def test_overflow_and_recovery(self):
        f=LineFramer(8);self.assertEqual(f.feed(b'x'*10000),[]);self.assertEqual(len(f.buffer),0)
        self.assertEqual(f.feed(b'bad\ngood\n'),[b'good']);self.assertEqual(f.overflows,1)

class CanTests(unittest.TestCase):
    def test_fragment_roundtrip_bounds(self):
        for payload in (b'x',encode(sample()),b'x'*1024):
            frames=fragment(payload,255);r=Reassembler()
            self.assertTrue(all(len(f)<=8 for f in frames))
            for f in frames:result=r.feed(100,f,0)
            self.assertEqual(result,payload.rstrip(b'\n'))
    def test_interleaved_nodes(self):
        a,b=fragment(b'abcdef'*3,1),fragment(b'ghijkl'*3,1);r=Reassembler();results=[]
        for fa,fb in zip(a,b):
            for cid,f in ((10,fa),(11,fb)):
                v=r.feed(cid,f,0)
                if v:results.append(v)
        self.assertEqual(results,[b'abcdef'*3,b'ghijkl'*3])
    def test_crc_corruption(self):
        fs=fragment(encode(sample()),1);fs[-1]=fs[-1][:-1]+bytes([fs[-1][-1]^1]);r=Reassembler()
        with self.assertRaises(ProtocolError):
            for frame in fs:r.feed(1,frame,0)
        self.assertEqual(len(r.pending),0)
    def test_missing_duplicate_order_timeout(self):
        fs=fragment(encode(sample()),1)
        for mode in ('missing','duplicate','order','timeout','start'):
            with self.subTest(mode=mode):
                r=Reassembler();r.feed(1,fs[0],0)
                with self.assertRaises(ProtocolError):
                    if mode=='missing':r.feed(2,fs[1],0)
                    elif mode=='duplicate':r.feed(1,fs[1],0);r.feed(1,fs[1],0)
                    elif mode=='order':r.feed(1,fs[2],0)
                    elif mode=='timeout':r.feed(1,fs[1],1)
                    else:r.feed(1,fs[0],0)
    def test_memory_capacity(self):
        r=Reassembler(max_inflight=2);f=fragment(b'abcdefghijk',1)[0]
        r.feed(1,f,0);r.feed(2,f,0)
        with self.assertRaises(ProtocolError):r.feed(3,f,0)
        self.assertEqual(r.expire(1),2)

class SerialTests(unittest.TestCase):
    def test_reconnect_partial_read_shutdown(self):
        c=Clock();m=SensorManager(load_registry(),c);service=IntegrationService(m);stop=threading.Event();attempts=[]
        class Port:
            def __init__(self):self.parts=[b'100,2542,2540,',b'2,IDLE,0,1,1\n']
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,n):
                if self.parts:return self.parts.pop(0)
                stop.set();return b''
        def factory(*args,**kwargs):
            attempts.append(1)
            if len(attempts)==1:raise OSError('unplugged')
            return Port()
        w=SerialSource(service,'fake','serial:pressure',mode='pressure',stop=stop,serial_factory=factory,reconnect_s=0.001)
        w.start();w.join(2)
        self.assertFalse(w.is_alive());self.assertEqual(len(attempts),2)
        self.assertEqual(m.snapshot()['channels']['pressure']['value'],2)
        self.assertEqual(m.snapshot()['diagnostics']['transport_lost'],1)
    def test_oversize_and_malformed_recovery(self):
        c,m=setup_manager();service=IntegrationService(m);stop=threading.Event();chunks=[b'x'*1100+b'\n',b'bad\n',encode(sample())]
        class Port:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,n):
                if chunks:return chunks.pop(0)
                stop.set();return b''
        w=SerialSource(service,'fake','wire',stop=stop,serial_factory=lambda *a,**kw:Port());w.start();w.join(2)
        self.assertEqual(m.snapshot()['channels']['pressure']['value'],42)
        self.assertEqual(m.snapshot()['diagnostics']['framing_overflow'],1)
        self.assertEqual(m.snapshot()['diagnostics']['parse_error'],1)
