# Architecture and engineering review

## Why these boundaries

The physical driver knows how to speak to a chip; the integration manager should not. The manager knows whether a sample is usable; the dashboard should not invent that decision. This separation lets the team change an IMU, serial transport or screen without changing pressure logic.

Today the Raspberry Pi (or development PC) runs the manager. It has the memory, logging and debugging facilities needed for the integration owner. SAMD21 nodes retain acquisition timing, local initialization/calibration and sensor faults. We do not put Python on SAMD21 or assume a single MCU can service every peripheral at the required rate.

The diagram in the main README is the implemented flow. `docs/architecture.mmd` contains its Mermaid source.

## Ten responsibilities

| Responsibility | Concrete implementation | Owner |
|---|---|---|
| Drivers/acquisition | Preserved pressure firmware; `SensorDriver` C++ interface, mock and unavailable IMU drivers | Sensor-module developer |
| Transport | Serial worker, finite reads, incremental bounded lines; experimental CAN codec | Module developer + integration |
| Decode/validate | Pressure adapter, strict JSON decoder, registry validation | Integration |
| Sensor management | Locked manager, registered identities, sessions, sequences, faults, timeouts | Integration |
| Time/synchronization | Extended uptime, receive timing, excess-delay estimate, boot-scoped explicit mappings | Integration |
| Processing | Pure gated relative quaternion rotation calculation | Integration + algorithm owner |
| Unified state | Snapshot containing all configured channels, validity, reason, provenance, diagnostics | Integration |
| Pi host interface | CLI, `/api/state`, loopback dashboard | Integration / UI teammate |
| Diagnostics | Structured counters, last 100 events, wire logs, visible log failure | Integration |
| Simulation/test | Seeded generators, fault scenario, fake clocks/ports, native tests | Every module + integration |

## Data example: an actual pressure row

`5100,2542,2540,2,IDLE,0,1,1` enters from USB. The adapter understands that `raw=2542`, `baseline=2540`, and `delta=2` are counts. It emits an initial inferred-session hello if needed, then a `pressure_delta` measurement. The manager checks the registry, source binding, sequence, timestamp and flags. Its state exposes `value=2`, `unit=adc_count`, and `calibration=baseline`. No kPa conversion or breath validation takes place. If the next row is `5250,,,,CAL_REQUIRED,0,0,0`, the current value immediately becomes `null`, with an explicit error.

## Threading and deterministic behavior

One thread owns each serial connection. The simulator has a separate worker. Each message is parsed and applied under the manager's reentrant lock. A snapshot copies state while holding the same lock, so concurrent callers see a coherent aggregate. There is no assumption that updates from two nodes arrive in a fixed interleaving. Each node must serialize its own sequence order before transmission.

The clock is injectable in the manager and simulator. Unit tests advance it directly. Production uses `time.monotonic`; changing wall time cannot revive old samples. Simulation randomness is seeded per sensor, so disabling one generator does not change another's noise sequence.

The host is **not hard real-time**. Logging is synchronous and can add latency; the OS and Python threads have no hard deadline. The current low-rate USB proof of concept is the target. Before high-rate acquisition, characterize worst-case throughput/latency and move logging to a bounded queue with an explicit drop/backpressure policy if necessary. Avoid an unbounded queue that conceals increasing delay.

## Memory and overload

Incoming lines are capped at 1,024 bytes. A too-long line is discarded through the next newline, counted and reported. Partial lines survive serial timeouts; they are never parsed as complete packets. JSON nesting and numeric types are checked. There is no automatic registration of unknown nodes or sensor IDs.

The manager keeps one reading per configured sensor, a 100-event diagnostic ring, and up to 1,024 retired boot IDs per configured node. On reaching the boot-history cap it rejects further new sessions and requires an operator restart. The prototype CAN reassembler caps incomplete transfers and expires them. Log storage rotates rather than growing without bound. The browser retains 120 plotted points per channel and draws gaps for invalid/unavailable samples.

## Decisions from review

- **Keep pressure firmware unchanged:** its source and build config match the pinned upstream commit. The new adapter sits outside it.
- **Replace the earlier starter core:** retain its simple adapter concept, but add an explicit node lifecycle, strict payload validation, per-sensor timeouts, delayed-data handling, guarded derived data and separate service/UI boundaries.
- **Single canonical contract:** JSONL is the first wire representation. CAN framing feeds the same decoded contract; no processing logic depends on a CAN ID.
- **Do not silently substitute data:** physical ownership excludes that node from simulation; faults produce `null`, never synthetic fallback.
- **Separate failure dimensions:** node heartbeat updates node liveness only. Invalid samples supersede prior valid samples. Rejected messages do not refresh liveness or measurement age. Historical values are named `last_received_value` and are never the dashboard's current value.
- **Clock honesty:** no automatic clock synchronization is claimed. Shared-host simulation is mapped; independent physical IMUs are unsynchronized until measured mappings and mounting frames exist.
- **Simple extension:** new scalar/quaternion sensor registrations need no manager edit. A new data shape should add explicit validation and processing with contract tests.

## Scope boundary

There is no actuator command plane, monitor electrical interface, alarm system, ventilation classifier, airflow/volume calculation, SpO₂ optical driver, temperature hardware driver or CPR-depth inference. ECG, heart sound and RGB output modules are intentionally outside this sensor foundation. Their future telemetry can use the same contract. Commands should have their own request ID, acknowledgement, timeout and idempotence design before they drive hardware.
