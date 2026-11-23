"""Install official Bosch BHI360 SensorAPI and lite IMU firmware, no MCU access."""
from __future__ import annotations
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "lib" / "BHI360Vendor"
URL = "https://github.com/boschsensortec/BHI360_SensorAPI.git"
FIRMWARE = "Bosch_Shuttle3_BHI360_bsxsam_lite.fw.h"
PATCH_STAMP = "KEVIN_BHI360_PLATFORMIO_PORT_v1.txt"
# Minimal embedded SensorAPI source files; omit Bosch's COINES/verbose host examples.
DRIVER_SOURCES = (
    "bhi360.c",
    "bhi360_hif.c",
    "bhi360_event_data.c",
    "bhi360_virtual_sensor_conf_param.c",
    "bhi360_system_param.c",
    "bhi360_virtual_sensor_info_param.c",
)

def main():
    if (DEST / "src" / "bhi360.h").is_file() and (DEST / "src" / "bhi360" / FIRMWARE).is_file() and (DEST / PATCH_STAMP).is_file():
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
        # Three upstream static C99 designated initializer tables are not
        # needed in the Arduino C++ translation unit. Keep them unchanged
        # for Bosch's C .c source files; hide them only from C++.
        header = libsrc / "bhi360_event_data_defs.h"
        content = header.read_text(encoding="utf-8")
        regex = re.compile(
            r"^static const char \* const "
            r"(?:bhi360_event_data_multi_tap_string_out|"
            r"bhi360_event_data_head_gesture_string_out|"
            r"bhi360_event_data_wrist_gesture_detect_output)"
            r"\[\] = \{.*?\};",
            flags=re.DOTALL | re.MULTILINE,
        )
        content, patched = regex.subn(
            lambda m: "#ifndef __cplusplus\n"
                      + m.group(0)
                      + "\n#endif /* K.E.V.I.N.: C-only lookup table */",
            content,
        )
        if patched != 3:
            raise RuntimeError(
                f"Unexpected Bosch header layout: patched {patched} tables, expected 3"
            )
        header.write_text(content, encoding="utf-8")
        (libsrc / "bhi360").mkdir()
        shutil.copy2(fw, libsrc / "bhi360" / fw.name)
        shutil.copy2(repo / "LICENSE", staged / "LICENSE")
        (staged / "UPSTREAM_COMMIT.txt").write_text(f"{URL}\ncommit={commit}\nfirmware={FIRMWARE}\n", encoding="utf-8")
        # Bosch's bhi360_parse.c requires verbose.h and coines.h;
        # it is not needed for the FIFO callback we registered.
        for name in DRIVER_SOURCES:
            if not (libsrc / name).is_file():
                raise RuntimeError(f"Missing required Bosch driver source: {name}")
        library = {
            "name": "BHI360Vendor",
            "version": "2.3.1",
            "build": {
                "srcDir": "src",
                "includeDir": "src",
                "srcFilter": ["-<*>"] + [f"+<{name}>" for name in DRIVER_SOURCES],
            },
        }
        (staged / "library.json").write_text(
            json.dumps(library, indent=2) + "\n", encoding="utf-8"
        )
        (staged / PATCH_STAMP).write_text(
            "K.E.V.I.N. Arduino PlatformIO subset v1\n"
            "C-only string tables hidden from C++ translation units.\n"
            "Only six embedded Bosch driver files compiled; COINES parser excluded.\n"
            f"Official upstream git commit: {commit}\n",
            encoding="utf-8",
        )
        DEST.parent.mkdir(exist_ok=True)
        if DEST.exists():
            shutil.rmtree(DEST)
        shutil.copytree(staged, DEST)
        print("Installed PlatformIO-compatible Bosch SDK into", DEST)
        print("Bosch commit:", commit)
        print("Build only: platformio run -e b2_imu_accel")

if __name__ == "__main__":
    main()
