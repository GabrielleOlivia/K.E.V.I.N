# Chest BHI360 firmware-upload crash — captured 2026-11-16

**Status:** An actual BHI360 postmortem was retrieved from the CHEST IMU via SAMD21 firmware v0.8. The device is **not** running fusion firmware. For research/manikin use only.

## Setup
- Chest: SensorHub A1, SAMD21 SERCOM1 PA16/PA17; BHI360 I²C address 0x29
- Head: SensorHub B1, independent I²C bus, **not touched** during this test
- BHI360 chip ID: 0x7A, FUSER2 ID 0x89, silicon rev 0x02, ROM 0x142E (5166)
- Bosch SDK: BHI360 SensorAPI v2.3.1
- Firmware: `Bosch_Shuttle3_BHI360_bsxsam_lite.fw.h`, 82,648 bytes
- SAMD21 firmware: v0.8, manual CHEST-only test, 28 data bytes per I²C command write, 1 ms post-write pause

## Observed transfer failure
```text
# CHEST boot=0x18
# CHEST loading 82648 firmware bytes to BHI360 RAM; do not disconnect USB
# CHEST upload_progress accepted_writes=3 accepted_channel_bytes=84 failed_write=4 failed_after_bytes=84 elapsed_ms=14
# CHEST firmware_upload result=-3
# CHEST DIAG phase=firmware_upload_failed
# CHEST I2C stage=4 status=3 reg=0x0 length=28 api_intf_result=-1
# CHEST boot_status_read_result=0 boot=0x18 host_ready=1 verify_done=0 verify_error=0
# CHEST sensor_error_read_result=0 sensor_error=0x44
# CHEST debug_state_read_result=0 debug_state=0xB
# CHEST debug_value_read_result=0 debug_value=0x0
# CHEST POSTMORTEM_BEGIN
# CHEST postmortem_mode=auto_immediately_after_upload_failure
# CHEST postmortem_api_bind_result=0
# CHEST before_postmortem_error_result=0 error=0x44
# CHEST postmortem_result=0 postmortem_bytes=4300
```

Wire status 3 means data-byte NACK at register 0x00 (Host Channel 0). Bosch API returns -3, an I/O error. Sensor returns 0x44, an unhandled exception. **Causality remains unproven:** the crash may cause the NACK, rather than the NACK causing the crash.

## Decoded postmortem fields

Bosch datasheet BST-BHI360-DS000-03, Table 34, p.64: https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bhi360-ds000.pdf

**Important:** The v0.8 printout used incorrect `field_offset - 4` indices. The real payload returned by the API places fields directly at the documented offsets, as confirmed by the self-consistent values below. Fixed in v0.9.

| Payload offset | Field | Captured | Interpretation |
|---|---|---|---|
| 0x84 | Valid | 0x01 | Crash recorded |
| 0x85 | Flags | 0x06 | Stack info valid + stack dump included |
| 0x86–0x87 | Stack size | 0x1000 | 4096 bytes |
| 0x88–0x8B | Stack start | 0x00A05FDC | Raw address |
| 0x8C–0x8F | ERET | 0x00109F0C | Raw ARC register; not yet decoded |
| 0x90–0x93 | ERBTA | 0x009C2788 | Raw ARC register |
| 0x94–0x97 | ERSTATUS | 0x8000004E | Raw ARC register |
| 0x98–0x9B | ECR | 0x00020100 | Raw ARC exception register; not yet decoded |
| 0x9C–0x9F | EFA | 0x00109F0C | Raw ARC register |
| 0xA0–0xA3 | Diagnostic | 0x00000002 | Power-state subfield = 2 (active), no memory-access-error bits set |
| 0xA4–0xA7 | Icause | 0x00000016 | Raw ARC interrupt/exception register |
| 0xA8 | Debug Value | 0x00 | Raw host debug value |
| 0xA9 | Debug State | 0x0B | As also seen via host debug register |
| 0xAA | Error Reason | 0x00 | Snapshot field, distinct from live 0x44 |
| 0xAD | Reset Reason | 0x04 | Watchdog timeout or fatal exception (see ECR) |
| 0xAF | Error Report | 0x44 | Unhandled interrupt |

**Do not conclude the image, power supply, or I²C wires are defective without additional evidence.** A read-only preflight works on both sensors; the firmware upload path does not.

## Captured first 224 bytes only

The Bosch API reported 4300 bytes, but v0.8 deliberately printed only the first 224 bytes. The full 4096-byte stack was not emitted to Serial and is not saved in this repository.

```text
# DUMP 0: 98 5E A0 00 00 00 00 00 28 00 00 00 07 00 00 00
# DUMP 10: 00 04 00 00 00 00 F0 00 FC 47 12 00 01 00 00 00
# DUMP 20: 7F 00 00 00 00 00 00 00 B0 42 01 00 01 00 00 00
# DUMP 30: 00 01 00 00 20 5C A0 00 01 00 00 00 00 40 12 00
# DUMP 40: E0 5E A0 00 D8 42 01 00 58 53 A0 00 00 85 21 10
# DUMP 50: 20 40 0D 88 00 02 20 0A 08 00 00 40 02 02 30 02
# DUMP 60: 1A 00 02 32 08 42 08 01 1C 5C A0 00 2C 6F A0 00
# DUMP 70: B8 6B A0 00 16 1D 10 00 05 00 84 00 04 27 10 00
# DUMP 80: F2 29 10 00 01 06 00 10 DC 5F A0 00 0C 9F 10 00
# DUMP 90: 88 27 9C 00 4E 00 00 80 00 01 02 00 0C 9F 10 00
# DUMP A0: 02 00 00 00 16 00 00 00 00 0B 00 00 00 04 00 44
# DUMP B0: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
# DUMP C0: 00 00 00 00 81 BE 24 CC 80 37 AF 56 DD A6 FC 10
# DUMP D0: 4A 6A E2 52 CB B0 8F C6 D0 EC F5 BD 8B F5 75 E8
```

Next debugging should prioritize a review of I²C command-channel upload framing, the ARC exception fields, image compatibility, and electrical power/signal integrity. **Do not repeat firmware uploads merely to gather the same evidence.**
