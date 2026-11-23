"""Install official Bosch BHI360 SensorAPI and lite IMU firmware, no MCU access."""
from __future__ import annotations
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "lib" / "BHI360Vendor"
URL = "https://github.com/boschsensortec/BHI360_SensorAPI.git"
FIRMWARE = "Bosch_Shuttle3_BHI360_bsxsam_lite.fw.h"

def main():
    if (DEST / "src" / "bhi360.h").is_file() and (DEST / "src" / "bhi360" / FIRMWARE).is_file():
        print("SDK already installed:", DEST)
        return
    with tempfile.TemporaryDirectory(prefix="kevin_b2_bosch_") as tmp:
        repo = Path(tmp) / "upstream"
        subprocess.run(["git", "clone", "--depth", "1", "--quiet", URL, str(repo)], check=True)
        commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
        source = repo / "source"
        fw = repo / "firmware" / "bhi360" / FIRMWARE
        if not ((source / "bhi360.h").is_file() and fw.is_file() and (repo / "LICENSE").is_file()):
            raise RuntimeError("Unexpected official Bosch repository layout; nothing installed")
        staged = Path(tmp) / "staged"
        libsrc = staged / "src"
        libsrc.mkdir(parents=True)
        for pattern in ("*.c", "*.h"):
            for file in source.glob(pattern):
                shutil.copy2(file, libsrc / file.name)
        (libsrc / "bhi360").mkdir()
        shutil.copy2(fw, libsrc / "bhi360" / fw.name)
        shutil.copy2(repo / "LICENSE", staged / "LICENSE")
        (staged / "UPSTREAM_COMMIT.txt").write_text(f"{URL}\ncommit={commit}\nfirmware={FIRMWARE}\n", encoding="utf-8")
        (staged / "library.json").write_text('{"name":"BHI360Vendor","version":"2.3.1","build":{"srcDir":"src","includeDir":"src"}}\n', encoding="utf-8")
        DEST.parent.mkdir(exist_ok=True)
        if DEST.exists():
            shutil.rmtree(DEST)
        shutil.copytree(staged, DEST)
        print("Installed Bosch SDK into", DEST)
        print("Bosch commit:", commit)
        print("Build only: platformio run -e b2_imu_accel")

if __name__ == "__main__":
    main()
