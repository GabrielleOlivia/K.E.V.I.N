#!/usr/bin/env python3
"""Offline audit of the *pinned official* Bosch BHI360 bsxsam_lite image.

Usage, from hardware/imu/dual-motion on Windows:
    py -3 .\scripts\audit-firmware.py

No hardware interaction, serial ports, firmware upload, or extra packages.
The test compares the locally installed C array against Bosch's .fw binary,
then checks that the binary matches the Git blob in SensorAPI tag v2.3.1.
It reconstructs the first few *host-side* command packets as in
bhi360_hif_exec_cmd_generic() with a 28-byte write limit.
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

FIRMWARE_NAME = "Bosch_Shuttle3_BHI360_bsxsam_lite"
OFFICIAL_IMAGE_BYTES = 82648
OFFICIAL_FW_GIT_BLOB = "9653806deb40032f606d78b72ed6b8d7849da816"
WRITE_BYTES = 28  # data bytes, excluding the I2C register address
BOOTLOADER_ROM_SEEN_ON_HARDWARE = 0x142E


def fail(message: str) -> int:
    print("FAIL:", message)
    return 1


def git_blob_sha1(data: bytes) -> str:
    """Same object hash that git hash-object uses for a binary blob."""
    prefix = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(prefix + data).hexdigest()


def read_c_firmware_array(path: Path) -> bytes:
    source = path.read_text(encoding="utf-8")
    match = re.search(
        r"\bbhi360_firmware_image\s*\[\s*\]\s*=\s*\{(.*?)\}",
        source,
        flags=re.DOTALL,
    )
    if not match:
        raise ValueError("Cannot locate Bosch bhi360_firmware_image[] array")
    body = match.group(1)
    tokens = re.findall(r"\b0[xX][0-9a-fA-F]{1,2}\b", body)
    if not tokens:
        raise ValueError("Bosch C array has no hexadecimal image bytes")
    # Reject stray non-array syntax instead of quietly ignoring altered bytes.
    remainder = re.sub(r"\b0[xX][0-9a-fA-F]{1,2}\b", "", body)
    if remainder.strip(" \r\n\t,"):
        raise ValueError("Unexpected text inside firmware array")
    return bytes(int(token, 16) for token in tokens)


def main() -> int:
    project = Path(__file__).resolve().parent.parent
    images = project / "include" / "bhi360"
    header = images / (FIRMWARE_NAME + ".fw.h")
    binary = images / (FIRMWARE_NAME + ".fw")

    print("K.E.V.I.N. BHI360 firmware audit (offline, NO sensor writes)")
    print("Project:", project)
    if not header.is_file() or not binary.is_file():
        return fail(
            "Missing Bosch .fw or .fw.h file. Run "
            "powershell -ExecutionPolicy Bypass -File .\\scripts\\setup-bosch.ps1 "
            "from hardware\\imu\\dual-motion, then rerun this audit."
        )
    try:
        header_bytes = read_c_firmware_array(header)
        binary_bytes = binary.read_bytes()
    except (OSError, ValueError) as exc:
        return fail(str(exc))

    print("C header bytes:", len(header_bytes))
    print("Bosch binary bytes:", len(binary_bytes))
    if header_bytes != binary_bytes:
        mismatch = next(
            (i for i, (a, b) in enumerate(zip(header_bytes, binary_bytes)) if a != b),
            min(len(header_bytes), len(binary_bytes)),
        )
        return fail(f"C header does not match Bosch .fw binary at byte {mismatch}")

    if len(binary_bytes) != OFFICIAL_IMAGE_BYTES:
        return fail(
            f"Unexpected image size {len(binary_bytes)}, expected "
            f"{OFFICIAL_IMAGE_BYTES} from the tested Bosch v2.3.1 image"
        )
    if len(binary_bytes) % 4:
        return fail("Firmware image is not 32-bit word-aligned")

    actual_git_sha = git_blob_sha1(binary_bytes)
    print("Bosch .fw Git blob SHA-1:", actual_git_sha)
    if actual_git_sha != OFFICIAL_FW_GIT_BLOB:
        return fail("Local .fw does not match Bosch SensorAPI tag v2.3.1")
    print("PASS: C array matches unmodified official Bosch .fw image")

    magic = int.from_bytes(binary_bytes[:2], "little")
    print(f"Firmware magic: 0x{magic:04X} (Bosch expected 0x662B)")
    if magic != 0x662B:
        return fail("Invalid BHI360 image magic")

    # An observation, not a documented parser for Bosch's binary header.
    observed_rom_bytes = int.from_bytes(binary_bytes[0x60:0x62], "little")
    print(
        f"Image bytes at offsets 0x60..0x61: 0x{observed_rom_bytes:04X}; "
        f"device ROM reported 0x{BOOTLOADER_ROM_SEEN_ON_HARDWARE:04X} "
        "(not independently verified as a version field)"
    )

    word_count = len(binary_bytes) // 4
    if word_count > 65535:
        return fail("Firmware word count exceeds Bosch 16-bit command length")
    # Per Bosch Table 36: 0x0002 command, 16-bit image length in 32-bit words.
    stream = b"\x02\x00" + word_count.to_bytes(2, "little") + binary_bytes
    packets = [
        stream[offset: offset + WRITE_BYTES]
        for offset in range(0, len(stream), WRITE_BYTES)
    ]
    if any(len(packet) > WRITE_BYTES or len(packet) % 4 for packet in packets):
        return fail("Generated packet length is invalid or not 4-byte aligned")
    if b"".join(packets) != stream:
        return fail("Packet reconstruction lost or duplicated bytes")

    print(f"Upload command bytes: {stream[:4].hex(' ').upper()}")
    print(f"Word count: {word_count}; packet size: {WRITE_BYTES} data bytes")
    print(f"Total command-channel bytes: {len(stream)}; packets: {len(packets)}")
    for index, packet in enumerate(packets[:4], start=1):
        print(f"Packet {index:02d}: {packet.hex(' ').upper()}")

    firmware_accepted_on_original_test = 3 * WRITE_BYTES - 4
    print(
        "Observed hardware: first 3 packet ACKs = "
        f"{firmware_accepted_on_original_test} firmware bytes + 4 command bytes."
    )
    print(
        "Packet 4 starts at firmware byte offset "
        f"{firmware_accepted_on_original_test}."
    )
    print("Image SHA-256:", hashlib.sha256(binary_bytes).hexdigest())
    print("PASS: local firmware image and expected host-side packet framing")
    print(
        "LIMIT: this does NOT test SAMD21 I2C signals, supply stability, "
        "or the BHI360 bootloader's internal crash cause."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
