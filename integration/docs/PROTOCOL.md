# Sensor protocol v1

This is the **new foundational wire contract**, distinct from the undocumented `protocol_version: 1` dictionaries in the earlier virtual starters. Existing pressure CSV remains supported through an adapter. Old starter JSON dictionaries are rejected, not silently reinterpreted. See `examples/protocol.jsonl` for complete, executable examples.

## Serial framing and envelope

One UTF-8 JSON object per LF-terminated line; CRLF is accepted. Maximum JSON length is 1,024 bytes, excluding newline. No NaN, Infinity, duplicate JSON keys, extra top-level fields, nested metadata beyond five levels, or boolean-as-number values. An invalid measurement uses JSON `null`. Field defaults below are applied when omitted; producers should include the relevant status fields explicitly.

| Field | Type / allowed values | Meaning |
|---|---|---|
| `v` | integer `1`, required | Wire version |
| `type` | `hello`, `measurement`, `heartbeat`, `status`, `fault`; required | Message category |
| `node_id` | identifier, required | Registered MCU/module identity |
| `boot_id` | identifier, required | Unique boot/session identity |
| `seq` | uint32, required | Node-wide transmission sequence |
| `t_ms` | uint32, required | Node uptime timestamp |
| `clock` | `uptime_ms`, required | Clock domain; never assumed UTC |
| `sensor_id` | identifier or null, default null | One registered sensor for a measurement or sensor-specific status |
| `measurement` | identifier or null | Registry measurement type |
| `value` | finite scalar, list of up to four numbers, or null | Registry shape validates scalar vs quaternion |
| `unit` | string, max 24 characters, or null | Must exactly match registry |
| `status` | `ok`, `invalid`, `fault`; default `ok` | Source acquisition condition |
| `valid` | boolean, default false | Only an `ok` measurement can be true |
| `calibration` | `unknown`, `uncalibrated`, `calibrating`, `baseline`, `calibrated`, `not_required`, `simulated` | Calibration provenance |
| `error` | null or string of 1–160 characters | Required for invalid/fault status; stable codes recommended |
| `meta` | bounded JSON object, default `{}` | Diagnostics and module-specific metadata |

Identifiers use `[A-Za-z0-9_.:-]`, 1–64 characters. UUID hex strings are valid boot IDs. Source/transport identity and reception time are **host-owned**, not trusted wire fields. Registry node/type/unit mismatches are rejected before state changes.

A successful zero reading is allowed. An unavailable reading must not use zero. A baseline accepted by the legacy pressure algorithm is only accepted for sensors whose registry sets `baseline_allowed`. A physical sensor requiring calibration cannot bypass it by labelling itself `not_required`. `simulated` calibration is usable only for a node whose hello explicitly declares simulation. Per-node provenance is displayed.

## Message lifecycle

1. Initialize transport and driver. Choose a new boot ID. Send `hello`; a measurement cannot establish an unknown boot.
2. Send measurement messages, with a single node-wide sequence incrementing for every message type. A sample timestamp records acquisition (or explicitly documented read completion), not transmission.
3. Send heartbeat, typically once per second. A healthy heartbeat does not assert that a sensor's measurement or calibration is valid.
4. Send `fault` with `status=fault` and an error to latch a fault. Use `sensor_id` for one sensor or null for the node.
5. Send `status` with `status=ok` to explicitly clear a latched node fault. A new valid sensor measurement clears a sensor fault. Clearing a fault does not update the old sample's timestamp.
6. Repeat `hello` periodically, with a fresh increasing sequence number, so a host joining mid-run can discover the current boot. Same-boot hello does not clear readings or faults.

Messages within a node must be transmitted in nondecreasing `t_ms` order; repeated timestamps across different sensors/control messages are allowed. A newer sequence with the same sensor's prior acquisition timestamp is rejected. Do not publish an old queued sample after a newer-timestamp heartbeat; drain/discard old acquisition data first. Sequence and timestamp deltas use half-range modular comparison. A legitimate counter advance must be less than 2³¹; resynchronize after a longer gap.

A new boot ID is accepted only via hello; all readings for that node are cleared. Retired IDs cannot return during the host process lifetime. Duplicate/out-of-order packets do not refresh freshness or connection time. Sequence gaps are counted; their contents cannot be recovered by this telemetry protocol. This is loss-visible streaming, not reliable command delivery. State is not persisted across a host restart.

## Timing: three different times

- **Acquisition time:** node `t_ms`, extended by the host across normal uint32 rollover. The old pressure firmware specifically stamps **read completion**, after the conversion/read.
- **Reception time:** host monotonic seconds recorded after complete line reception/decoding. Used for link health and local ordering. A restarted host begins a new time domain.
- **Logged UTC:** human-readable audit time. Never used for freshness decisions.

For unsynchronized nodes, the host remembers the minimum observed `receive_time - node_uptime` per boot and estimates **excess delay** above that minimum. Measurement age is elapsed host time since reception plus this estimated excess delay. An ordered backlog can therefore be stale immediately on arrival. Repeated/out-of-order sequences are rejected independently.

This is **not synchronization** and does not establish absolute one-way delay. The first buffered sample and constant transport delay are unknowable from these fields; drift also affects the estimate. The dashboard's `active` means valid within this policy, not proof of accurate physical acquisition time. Native serial has no end-to-end checksum; deploy an envelope CRC/binary framing if raw UART noise testing shows it is needed. Numeric corruption that remains valid JSON cannot always be detected.

`SensorManager.install_time_mapping(node_id, boot_id, offset_s, uncertainty_s, lifetime_s)` supports externally measured clock mappings. A mapping converts extended node seconds to host monotonic seconds, is bound to the current boot, and expires. Mapped future timestamps outside uncertainty are rejected. Clock synchronization exchanges themselves are future work, not implemented. Simulation can supply an exact mapping because all generators use the host's clock.

Relative head/chest geometry requires two valid quaternions, unexpired mappings, matching `frame_id`, `mounting_calibrated=true`, and sample skew plus both uncertainties no greater than 100 ms. This is a configurable engineering gate in the processing function, not a clinically justified tolerance. No cross-node pitch subtraction is performed when clocks or frames are unknown.

## Channel state precedence

| Condition | State | Current value |
|---|---|---|
| No node hello | `missing` | null |
| Explicit transport loss or node age >= disconnect timeout | `disconnected` | null |
| Latched node/sensor fault | `faulty` | null |
| Hello but no measurement | `initializing` | null |
| Measurement age >= stale timeout | `stale` | null |
| Source invalid or required calibration missing | `invalid` | null |
| All checks pass | `active` | latest value |

Timeouts are registry settings tied to expected reporting rates, not physiological limits. A heartbeat-only node can keep its connection alive while its sensor remains stale. Check `reason`, calibration and diagnostics as well as state.

## Legacy pressure translation

The exact eight-column header and comment lines are accepted; the adapter may join midstream without a header. Flags must be 0/1. Signed 16-bit raw/base values, empty invalid fields, event states, `delta=raw-baseline`, count and timestamp ranges are checked. Invalid read/calibration rows remain visible and null-valued. Comments are logged and reported, not parsed as medical events.

The firmware has no sequence or boot identity. The adapter synthesizes them. A port-open session, repeated header or backwards timestamp (outside a plausible uint32 wrap) begins a new inferred session. Equal timestamps are rejected. These are explicit **legacy limitations**: the adapter cannot prove MCU restart, detect every lost CSV row, or distinguish a genuinely replayed old log injected into a fresh serial session. The common native protocol removes that ambiguity for future modules.

## CAN: experimental software codec only

MCP2515 supports Classic CAN with **0–8 payload bytes**, not CAN FD. The included Python codec in `kevin/transports/can.py` is tested but not connected to an MCP2515 or SocketCAN runtime. It exists to exercise the transport boundary and fragmentation contract. It is not a validated team CAN standard.

One CAN arbitration ID must belong to one sender/stream. Byte 0 is an 8-bit transfer ID, byte 1 the zero-based fragment index, byte 2 total fragments, and bytes 3–7 carry up to five envelope bytes. The envelope is a two-byte big-endian JSON byte length, the UTF-8 JSON bytes without newline, and a four-byte big-endian CRC32 of those bytes (Python `zlib.crc32`). Frames have eight bytes except the final frame; there is no padding.

The receiver keys transfers by CAN ID and transfer ID, requires fragment zero first and strict order, rejects duplicate/mismatched fragments, validates length/CRC, and times out unfinished transfers after 500 ms. At most 16 are held by default. Fragment loss discards that message; subsequent telemetry can recover. Do not reuse a transfer ID on a CAN ID until the earlier transfer and timeout window have ended. A gateway must bind CAN IDs to registered node IDs; that mapping and driver are not implemented here.

JSON fragmentation is expensive: a 400-byte message needs 82 Classic-CAN frames. A production bus will probably need a compact binary mapping or existing transport standard, selected after actual rates and priorities are agreed. Keep the decoded message model stable when that wire representation changes. At UART 115200 8N1, the theoretical byte budget is about 11,520 bytes/s; six 400-byte streams at 10 Hz exceed it. USB CDC baud settings do not by themselves define USB throughput. Measure the actual link, set per-node rates and reserve bandwidth before combining nodes.

Reference: [Microchip MCP2515 family datasheet](https://ww1.microchip.com/downloads/en/DeviceDoc/MCP2515-Family-Data-Sheet-DS20001801K.pdf).
