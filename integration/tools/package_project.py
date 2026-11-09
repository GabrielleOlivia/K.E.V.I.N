"""Build a source-only ZIP, with per-file SHA256 inventory, from this project."""
from pathlib import Path
import hashlib
import zipfile

root = Path(__file__).resolve().parents[1]
excluded = {'.git', '.pio', '.venv', '__pycache__', 'logs', 'build', 'dist'}

def files():
    return sorted(p for p in root.rglob('*') if p.is_file()
                  and not excluded.intersection(p.relative_to(root).parts)
                  and not any(part.endswith('.egg-info') for part in p.relative_to(root).parts)
                  and p.suffix not in ('.pyc', '.zip') and p.name != 'SHA256SUMS.txt')

inventory = '\n'.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(root).as_posix() for p in files())+'\n'
(root/'SHA256SUMS.txt').write_text(inventory, encoding='utf-8')
output = root.parent/'KEVIN_Sensor_Integration_v0.3.1.zip'
with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
    for p in files()+[root/'SHA256SUMS.txt']:
        archive.write(p, (Path(root.name)/p.relative_to(root)).as_posix())
print(output)
print('ZIP SHA256: '+hashlib.sha256(output.read_bytes()).hexdigest())
