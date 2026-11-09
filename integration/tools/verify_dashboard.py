"""Optional browser QA: needs Playwright and Chromium, not a runtime dependency."""
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parents[1]
with socket.socket() as sock:
    sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
with tempfile.TemporaryDirectory() as tmp:
    proc=subprocess.Popen([sys.executable,'-m','kevin','--port',str(port),'--log',str(Path(tmp)/'log.jsonl')],cwd=root,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        url='http://127.0.0.1:'+str(port)
        for attempt in range(100):
            try:
                urllib.request.urlopen(url+'/api/state',timeout=.2).close();break
            except OSError:time.sleep(.05)
        with sync_playwright() as p:
            options={'headless':True}
            if shutil.which('chromium'):options['executable_path']=shutil.which('chromium')
            browser=p.chromium.launch(**options)
            page=browser.new_page(viewport={'width':1280,'height':1100})
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(url);page.wait_for_selector('.card')
            assert page.locator('.card').count()==6
            card=page.locator('.card').filter(has=page.get_by_role('heading',name='pressure',exact=True))
            card.locator('input').uncheck()
            page.wait_for_function("[...document.querySelectorAll('.card')].find(e=>e.querySelector('h2').textContent==='pressure').querySelector('.badge').textContent==='stale'",timeout=7000)
            page.screenshot(path=str(Path(tempfile.gettempdir())/'kevin-dashboard.png'),full_page=True)
            card.locator('input').check()
            page.wait_for_function("[...document.querySelectorAll('.card')].find(e=>e.querySelector('h2').textContent==='pressure').querySelector('.badge').textContent==='active'",timeout=7000)
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            proc.terminate();proc.wait(timeout=3)
            page.wait_for_function("document.querySelector('#connection').textContent.includes('HOST DISCONNECTED')",timeout=5000)
            assert all(v=='—' for v in page.locator('.number').all_text_contents())
            assert not errors,errors
            browser.close()
            print('PASS: 6 cards, simulation disable/stale/recovery, mobile fit, host-loss invalidation; no JS errors.')
    finally:
        if proc.poll() is None:proc.terminate();proc.wait(timeout=3)
