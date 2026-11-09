"""Composition root and CLI. All sensing and management live in other modules."""
import argparse
import math
import importlib.util
from pathlib import Path
import sys
import threading
import time
from .registry import load_registry
from .manager import SensorManager
from .service import IntegrationService
from .eventlog import EventLog
from .dashboard import create_server
from .transports.serial_source import SerialSource
from .adapters.pressure_csv import PressureCSV
from .transports.framing import LineFramer
from .simulation.engine import Simulator


def replay_pressure(service, path, stop, speed=1.0):
    adapter = PressureCSV()
    previous = None
    def lines(stream):
        framer = LineFramer()
        while True:
            chunk = stream.read(4096)
            if not chunk:
                if framer.buffer or framer.discarding:
                    service.manager.diagnostic('replay_partial_line', 'incomplete final line discarded')
                return
            before = framer.overflows
            for line in framer.feed(chunk):
                yield line
            if framer.overflows != before:
                service.manager.diagnostic('framing_overflow', 'pressure replay')
    try:
        with Path(path).open('rb') as stream:
            for line in lines(stream):
                if stop.is_set():
                    return
                messages = service.decode_line(line, 'replay:pressure', adapter)
                samples = [m for m in messages if m.type == 'measurement']
                ticks = samples[-1].t_ms if samples else None
                if ticks is not None and previous is not None:
                    delta = (ticks-previous) & 0xFFFFFFFF
                    if delta < 0x80000000 and stop.wait(delta/1000/speed):
                        return
                if ticks is not None:
                    previous = ticks
                for message in messages:
                    service.receive(message,'replay:pressure')
    except OSError as exc:
        service.manager.transport_lost('replay:pressure', str(exc))
        service.record('replay_failed', error=str(exc))
        return
    service.manager.diagnostic('replay_complete','end of file; samples will become stale')


def parser():
    p = argparse.ArgumentParser(description='K.E.V.I.N. sensor integration — training equipment')
    p.add_argument('--mode', choices=['simulate','physical','mixed','replay'], default='simulate')
    p.add_argument('--registry',help='JSON registry; defaults to bundled six sensors')
    p.add_argument('--disable',default='',help='comma-separated simulated sensor IDs')
    p.add_argument('--scenario',choices=['normal','demo'],default='normal')
    p.add_argument('--seed',type=int,default=7)
    p.add_argument('--pressure-port',help='existing CSV firmware port, e.g. COM3 or /dev/ttyACM0')
    p.add_argument('--jsonl-port',action='append',default=[],metavar='NODE=PORT',help='repeat for additional protocol v1 nodes')
    p.add_argument('--example-port',action='append',default=[],metavar='NODE=PORT',help='mock firmware only: host assigns SESSION on port open')
    p.add_argument('--pressure-file',help='existing CSV log for replay mode')
    p.add_argument('--speed',type=float,default=1.0,help='replay rate multiplier')
    p.add_argument('--port',type=int,default=8765,help='local dashboard port')
    p.add_argument('--no-web',action='store_true')
    p.add_argument('--duration',type=float,default=0,help='seconds; 0 runs until Ctrl+C')
    p.add_argument('--log',default='logs/session.jsonl')
    return p


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    if not math.isfinite(args.duration) or args.duration < 0 or not 0 < args.speed < 10000:
        p.error('duration must be nonnegative; speed must be 0..10000')
    specs = load_registry(args.registry)
    nodes = {s.node_id for s in specs}
    sources, serials = {}, []
    if args.pressure_port:
        if not any(s.sensor_id == 'pressure' and s.node_id == 'pressure_node' for s in specs):
            p.error('legacy pressure mode requires pressure/pressure_node in registry')
        sources['pressure_node'] = 'serial:pressure'
        serials.append((args.pressure_port,'serial:pressure','pressure',False))
    for items, handshake in ((args.jsonl_port,False),(args.example_port,True)):
        for item in items:
            if '=' not in item:
                p.error('port assignment must be NODE=PORT')
            node, port = item.split('=',1)
            if node not in nodes or node in sources or not port:
                p.error('unknown/duplicate node or empty port: '+node)
            sources[node] = 'serial:'+node
            serials.append((port,sources[node],'jsonl',handshake))
    if len({x[0] for x in serials}) != len(serials):
        p.error('one serial reader per physical port')
    if serials and args.mode not in ('physical','mixed'):
        p.error('serial inputs require --mode physical or mixed')
    if args.mode == 'physical' and not serials:
        p.error('physical mode needs at least one serial port')
    if serials and importlib.util.find_spec('serial') is None:
        p.error('install physical input dependency: python -m pip install -r requirements-serial.txt')
    if args.mode == 'replay':
        if not args.pressure_file or not Path(args.pressure_file).is_file():
            p.error('replay mode requires an existing --pressure-file')
        sources['pressure_node'] = 'replay:pressure'
    elif args.pressure_file:
        p.error('--pressure-file requires --mode replay')
    sim_specs = [s for s in specs if s.node_id not in sources] if args.mode in ('simulate','mixed') else []
    disabled = set(filter(None,args.disable.split(',')))
    if disabled - {s.sensor_id for s in sim_specs}:
        p.error('--disable contains a sensor not assigned to simulation')
    for s in sim_specs:
        sources[s.node_id] = 'sim:'+s.node_id
    for node in nodes:
        sources.setdefault(node, 'disabled:'+node)
    stop = threading.Event()
    manager = SensorManager(specs,expected_sources=sources)
    log = EventLog(args.log)
    service = IntegrationService(manager,log)
    simulator = Simulator(service,sim_specs,enabled={s.sensor_id for s in sim_specs}-disabled,
                          seed=args.seed,scenario=args.scenario) if sim_specs else None
    workers, server, server_thread = [], None, None
    try:
        if not args.no_web:
            server = create_server(service,simulator,port=args.port)
            server_thread = threading.Thread(target=server.serve_forever,daemon=True)
            server_thread.start()
            print('Dashboard: http://127.0.0.1:'+str(server.server_port),flush=True)
        if simulator:
            workers.append(threading.Thread(target=simulator.run,args=(stop,),daemon=True,name='simulation'))
        for port, source, mode, handshake in serials:
            workers.append(SerialSource(service,port,source,mode,stop=stop,session_handshake=handshake))
        if args.mode == 'replay':
            workers.append(threading.Thread(target=replay_pressure,args=(service,args.pressure_file,stop,args.speed),daemon=True,name='replay'))
        for worker in workers:
            worker.start()
        print('Mode: '+args.mode+' | Ctrl+C stops | Log: '+args.log,flush=True)
        started = time.monotonic()
        while not stop.wait(0.5):
            state = service.snapshot()
            service.record('state',state=state)
            if args.no_web:
                print(' | '.join(s+':'+v['state']+'='+str(v['value'])+' '+v['unit'] for s,v in state['channels'].items()),flush=True)
            for worker in workers:
                if not worker.is_alive() and worker.name != 'replay':
                    raise RuntimeError('acquisition worker stopped unexpectedly: '+worker.name)
            if args.duration and time.monotonic()-started >= args.duration:
                break
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        for worker in workers:
            if worker.ident is not None:
                worker.join(timeout=3)
        if server:
            server.shutdown()
            server.server_close()
            server_thread.join(timeout=2)
        service.record('shutdown',state=service.snapshot())
        log.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
