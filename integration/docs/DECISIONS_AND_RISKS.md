# Decisions, assumptions and unresolved risks

## Evidence and reuse

Repository inspected: [K.E.V.I.N., pressure branch](https://github.com/GabrielleOlivia/K.E.V.I.N/tree/feature/pressure-logging), pinned at `80d4b6915a86d1c64f27daf8a2a1b0bb9d1dfbf2`.

`firmware/pressure_legacy/UPSTREAM_MANIFEST.json` records the Git blob SHA of every included upstream text file. Source, configuration, native tests, notes and the recorded CSV were preserved. The generated upstream plot image was omitted; its optional plotting script remains, and needs matplotlib if you choose to regenerate it. The repository itself has not been modified or pushed.

The project source brief confirms the semester project, clients and aim of improving sensor/monitor interfaces and reliability. It does not establish new sensor pins, supply levels, pressure transfer functions or IMU register settings.

Both earlier ZIPs were inspected: `KEVIN_Virtual_Sensor_Integration_Starter.zip` and `KEVIN_Sensor_Integration_Base_v02.zip`. They provided a useful six-channel demonstration, null-on-missing behavior, an initial pressure adapter and a simple dashboard. The second added live pressure serial input and JSONL support. Their core used a single two-second stale timeout, accepted boot changes without a handshake/history, did not distinguish stale from disconnected/faulted nodes, and combined independently timestamped IMU pitch values without alignment. Their serial reader used complete-line assumptions and had no bounded shutdown. Their internal JSON dictionaries lacked this package's complete versioned lifecycle contract. Those are technical reasons for a new core. The legacy CSV interface is retained; no promise is made that old starter Python imports or JSON dictionaries remain source-compatible.

## Implementation status

| Area | Implemented today | Still needs hardware or decisions |
|---|---|---|
| Pressure | Exact CSV adapter, flags/comments, recorded log replay, preserved firmware and tests | New host bench session, actual analog path and physical calibration |
| Native protocol | Strict JSONL, hello/measurement/heartbeat/status/fault, source binding | Teammate adoption; UART corruption policy if required |
| Lifecycle | Node boot/sequence handling, timeouts, invalidation, reconnect | Reset and serial-enumeration behavior of actual boards |
| Time | Receive/uptime separation, rollover, delay estimate, explicit mapping API and expiry | Measured clock synchronization exchange and drift budget |
| IMUs | Quaternion validation, gated relative rotation, C++ mock/unavailable interfaces | Exact BHI/BMI identity, vendor driver/firmware, frames/mounting and calibration |
| CPR/temp/SpO₂ | Simulated scalar inputs and registry interfaces | Actual hardware definitions, acquisition and calibration |
| CAN | Software fragment/reassembly/CRC tests | MCP2515 driver, transceiver, wiring, arbitration IDs, timing and compact encoding |
| Logging/dashboard | Local browser graphs/API, status, rotating JSONL | Longer bench runs; production UI/access policy if needed |
| Actuators/ECG/monitor | Architecture boundary documented | Separate command/electrical interface work |

## Major assumptions and risks

1. **Pressure is not volume.** Raw or calibrated pressure alone cannot establish delivered air volume or ventilation effectiveness. No conversion or medical event classification is implemented.
2. **Legacy boot identity is inferred.** CSV cannot uniquely identify a board boot, prove no lost rows, or detect every replay. Header/timestamp/session heuristics are documented.
3. **Physical clocks are unsynchronized by default.** Excess-delay estimates cannot reveal initial buffering or constant one-way latency. Relative geometry stays blocked without explicit mappings and frames.
4. **Example timing limits are engineering settings.** Stale/disconnect and geometry-skew thresholds need measurement against actual sample rates. They are not clinical limits.
5. **Hardware names are not proof.** BHI360 is documented by Bosch; the actual assembly must be inspected before choosing its API. No unknown register maps, wiring or transfer functions were invented.
6. **Host scheduling is soft real-time.** Synchronous file I/O, Python scheduling and serial buffering can add latency. Higher rates require throughput measurement and a bounded buffering policy.
7. **CAN is a migration point, not a completed bus implementation.** JSON fragmentation overhead can be unacceptable. Agree the traffic budget and binary/application mapping before deployment.
8. **No network trust mechanism on sensor wire.** Protocol identity/version/CRC are integrity tools, not authentication. Run on controlled bench links. The dashboard is loopback only.
9. **Power-loss persistence is limited.** Per-record flush is not per-record `fsync`; a crash can leave an incomplete final JSONL line. Sequence/retired-boot state is in-memory only. Logs rotate and must be archived.
10. **Expected-rate and numeric ranges vary by hardware.** Default pressure bounds reflect signed 16-bit differences and SpO₂ is bounded to 0–100 percent as a representation. No invented CPR-force or temperature clinical acceptance limits are applied.
11. **No physical hardware was available in this task.** Source-preservation checks, replay of an existing bench log, native C++ checks and cross-compilation do not substitute for bench validation.
12. **Packaging/platform limits.** Linux execution is tested here; Windows and Raspberry Pi OS instructions use standard-library interfaces but require target-device execution. Hardware serial permissions and ports are environment-specific.

## Next decisions in order

1. Confirm today's flashed pressure revision and first physical adapter run.
2. Identify the IMU board and agree raw vs fused output and mounting conventions.
3. Measure actual rates and serial timing; set registry timeouts accordingly.
4. Establish the two-IMU synchronization procedure and uncertainty budget.
5. Choose the CAN architecture after counting nodes, bandwidth, power and fault-recovery requirements.
6. Define patient-response/actuator commands separately with acknowledgements and tested failure behavior.
