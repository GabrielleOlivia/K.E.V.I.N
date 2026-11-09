"""Local browser view; acquisition and decisions never run in HTTP handlers."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets


def create_server(service, simulator=None, host='127.0.0.1', port=8765):
    token = secrets.token_hex(24)
    assets = Path(__file__).with_name('web')

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def reply(self, code, data, content_type='application/json'):
            payload = json.dumps(data, allow_nan=False).encode() if content_type == 'application/json' else data
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            if self.path == '/api/state':
                state = service.snapshot()
                state['simulation_control'] = {'token':token, **simulator.control_state()} if simulator else None
                return self.reply(200,state)
            files = {'/':('index.html','text/html; charset=utf-8'),
                     '/app.js':('app.js','text/javascript; charset=utf-8'),
                     '/style.css':('style.css','text/css; charset=utf-8')}
            if self.path not in files:
                return self.reply(404, {'error':'not found'})
            name, kind = files[self.path]
            self.reply(200,(assets/name).read_bytes(),kind)

        def do_POST(self):
            if self.path != '/api/simulation' or simulator is None:
                return self.reply(404,{'error':'simulation control unavailable'})
            if self.headers.get('X-KEVIN-Token') != token:
                return self.reply(403,{'error':'invalid control token'})
            try:
                self.connection.settimeout(2)
                size = int(self.headers.get('Content-Length','0'))
                if not 0 < size <= 256:
                    raise ValueError('body must be 1..256 bytes')
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError('control must be an object')
                # Preserve existing toggle API, while adding explicitly scoped
                # controls for synthetic sources only. Never reach hardware.
                if set(data) == {'sensor_id','enabled'} and type(data['enabled']) is bool:
                    simulator.set_enabled(data['sensor_id'],data['enabled'])
                elif set(data) == {'action','paused'} and data['action'] == 'pause':
                    simulator.set_paused(data['paused'])
                elif set(data) == {'action','scenario'} and data['action'] == 'scenario':
                    simulator.set_scenario(data['scenario'])
                elif set(data) == {'action','sensor_id','value'} and data['action'] == 'override':
                    simulator.set_override(data['sensor_id'],data['value'])
                else:
                    raise ValueError('unsupported simulation control')
                service.record('simulation_control', control=data)
                self.reply(200,{'ok':True, 'simulation_control':simulator.control_state()})
            except (ValueError, TypeError, KeyError, TimeoutError) as exc:
                self.reply(400,{'error':str(exc)})

    server = ThreadingHTTPServer((host,port),Handler)
    server.daemon_threads = True
    return server
