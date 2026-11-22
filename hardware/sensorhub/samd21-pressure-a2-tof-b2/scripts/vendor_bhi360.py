"""Install Bosch BHI360 SensorAPI v2.x sources from its official GitHub repo.

Opt-in dependency bootstrap for the experimental K.E.V.I.N. live SensorHub.
Run from the project root: py -3 scripts/vendor_bhi360.py
This script does NOT flash, reset, or access the microcontroller.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
DEST = PROJECT / 'lib' / 'BHI360Vendor'
UPSTREAM = 'https://github.com/boschsensortec/BHI360_SensorAPI.git'
FIRMWARE = 'Bosch_Shuttle3_BHI360_bsxsam.fw.h'


def main():
    if (DEST / 'src' / 'bhi360.h').exists() and (DEST / 'src' / 'bhi360' / FIRMWARE).exists():
        print('Bosch API already installed:', DEST)
        return

    print('Cloning official Bosch BHI360 SensorAPI (no user ZIP needed).')
    with tempfile.TemporaryDirectory(prefix='bhi360_vendor_') as tmp:
        cloned = Path(tmp) / 'BHI360_SensorAPI'
        subprocess.run(['git', 'clone', '--quiet', '--depth', '1', UPSTREAM, str(cloned)], check=True)
        commit = subprocess.check_output(['git', '-C', str(cloned), 'rev-parse', 'HEAD'], text=True).strip()
        source = cloned / 'source'
        image = cloned / 'firmware' / 'bhi360' / FIRMWARE
        license_file = cloned / 'LICENSE'
        if not (source / 'bhi360.h').is_file() or not image.is_file() or not license_file.is_file():
            raise FileNotFoundError('Bosch upstream layout changed. No files installed.')
        build = Path(tmp) / 'staged'
        target = build / 'src'
        target.mkdir(parents=True)
        for ext in ('*.c', '*.h'):
            for entry in source.glob(ext):
                shutil.copy2(entry, target / entry.name)
        (target / 'bhi360').mkdir()
        shutil.copy2(image, target / 'bhi360' / FIRMWARE)
        shutil.copy2(license_file, build / 'LICENSE')
        (build / 'UPSTREAM_COMMIT.txt').write_text(
            f'{UPSTREAM}\ncommit={commit}\nfirmware={FIRMWARE}\n', encoding='utf-8'
        )
        (build / 'library.json').write_text('''{
  "name": "BHI360Vendor",
  "version": "2.3.1",
  "build": {"srcDir": "src", "includeDir": "src"}
}\n''', encoding='utf-8')
        DEST.parent.mkdir(parents=True, exist_ok=True)
        if DEST.exists():
            shutil.rmtree(DEST)
        shutil.copytree(build, DEST)
        print('Installed official Bosch source into:', DEST)
        print('Upstream commit:', commit)
        print('Next: platformio run -e kevin_live_sensors (build before any upload)')


if __name__ == '__main__':
    main()
