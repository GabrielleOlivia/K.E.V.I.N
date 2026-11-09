## Addendum — interactive dashboard v0.3.1 (9 November 2026)

The updated Python unit/system suite completed **78 tests (77 passed, 1 skipped)** in this sandbox. The skipped test was an environment-dependent native integration check if a required binary/build capability was unavailable; see test output for the exact skip. The new six integration-control tests cover synthetic sliders, quaternion geometry, pause/recovery, scenario reset, validation and HTTP controls. `node --check kevin/web/app.js` passed.

The `tools/verify_dashboard.py` Chromium test was attempted but did **not** complete: the sandbox blocked navigation to its localhost endpoint (`ERR_BLOCKED_BY_ADMINISTRATOR`). This is **not** evidence that visual or interactive browser behavior passed. Browser QA on Windows/Raspberry Pi remains an explicit follow-up.

The original 0.3.0 validation results below are historical evidence from the supplied archive; do not interpret them as rerun results for modified 0.3.1 components. No hardware testing occurred during this update.

---

# Validation record

Date: 9 November 2026. Execution environment: Linux x86-64; Python 3.12.14; g++ 14.2.0; PlatformIO Core 6.2.0. No physical boards or sensors were connected.

## Results

| Check | Result | Evidence / scope |
|---|---|---|
| Automated suite | **72 tests passed**, no skips in this environment | `validation/test_results.txt` |
| Original pressure native suite | Passed inside the automated suite | Original 12-case C++ program compiled with `-std=c++11 -Wall -Wextra -Werror` and executed |
| New C++ native checks | Passed | Mock/unavailable driver behavior, timestamp wrap, bounded serialization and invalid values |
| C++ → Python contract | Passed | Actual native executable stdout decoded and accepted by Python manager |
| Pressure SAMD21 build | **Succeeded** | `validation/pressure_platformio.txt`; upstream unpinned platform resolved to atmelsam 9.0.0 |
| Mock-node SAMD21 build | **Succeeded** | `validation/node_platformio.txt`; pinned atmelsam 8.3.0; rerun on final source |
| Pressure firmware size | 15,316 bytes flash; 3,788 bytes static RAM | Linker/build size report; excludes runtime stack demand |
| Mock-node firmware size | 42,840 bytes flash; 4,288 bytes static RAM | Linker/build size report; excludes runtime stack demand |
| Upstream file preservation | All 12 included upstream text files match their Git blob SHA | Manifest plus automated preservation test |
| Existing recorded bench log | Parsed successfully, including status/diagnostics | This reuses prior evidence; it is not new hardware testing |
| Standard-library-only startup | Passed | Subprocess uses `python -S -m kevin`, disabling site packages |
| Serial lifecycle | Passed with fake ports and **real pyserial over a POSIX pseudo-terminal** | Partial reads, malformed/oversized lines, reconnect, unplug and shutdown; no electrical UART tested |
| HTTP dashboard/API | Passed | Real local HTTP requests to HTML/JS/CSS and state/control endpoints, invalid token and physical-takeover rejection |
| JavaScript syntax | Passed | `node --check kevin/web/app.js` |
| Python compilation | Passed | `python -m compileall -q kevin tests` |
| Browser rendering/interactions | **Not completed: environment blocked Chromium startup** | `validation/browser_results.txt`; browser package download also failed before the installed Chromium fallback |

The deliberate log-failure test prints `LOGGING FAILED: I/O operation on closed file.` in the test transcript. That message is expected evidence that a logging failure is visible; the test passes.

## Test coverage

- Strict wire validation: envelope types, versions, identifiers, null values, NaN/Infinity, duplicate keys, payload size, nesting, engineering bounds and quaternion norms; 500 seeded random byte inputs.
- State: missing, initializing, active, stale, invalid, faulty, disconnected, recovery, fault latching/clearing, calibration requirements and snapshot isolation.
- Ordering: duplicate and reversed sequences, uint32 sequence/timestamp wrap, repeated acquisition times, old boot replay, new-boot clearing, transport bindings and unknown sensors.
- Time: delayed ordered packets, heartbeats without fresh readings, future mapped samples, expired mappings, and suppression of unsynchronized/misaligned geometry.
- Concurrency: eight simultaneous node workers, 800 measurement updates and coherent snapshots; concurrent log appends.
- Legacy pressure: exact CSV format, flags/empty fields, arithmetic consistency, calibration/fault rows, header/reset inference, comments, rollover and real recorded data.
- Simulation: six sources, deterministic noise, individual on/off, delayed packets, disconnection/reconnection, invalid input and simulator restart.
- Logging: valid JSONL records, rejected input, rotation and visible write failures.
- CAN codec: bounded fragments, maximum-sized payload, interleaved nodes, CRC corruption, missing/duplicate/out-of-order fragments, timeout and memory cap.
- Application: CLI errors, simulation without third-party dependencies, replay/provenance, malformed timestamp pacing, bounded replay lines and examples.

## Reproduce

```sh
python -m unittest discover -s tests -v
python -m compileall -q kevin tests
python -m platformio run -d firmware/pressure_legacy
python -m platformio run -d firmware/node_example
```

Optional visual QA on an unrestricted development computer:

```sh
python -m pip install playwright
python -m playwright install chromium
python tools/verify_dashboard.py
```

The optional script checks six cards, disabling/re-enabling a simulated stream, stale state, mobile width and null-value display when the host disappears. It was supplied but could not complete here because the sandbox denied a socket required by Chromium. It is not part of the 72 passing checks.

## Not established by these results

No SAMD21 upload or physical USB read; no live MCP3426/I2C timing or fault injection; no pressure-reference calibration; no IMU identification/vendor firmware/fusion validation; no physical head/chest synchronization or mounting calibration; no real CPR, temperature or optical sensing; no CAN controller/transceiver/bus-off test; no long-duration load, power-loss endurance, clinical or physiological validation. Windows and Raspberry Pi OS execution must be checked on their actual targets. Compilation is not hardware validation.

The optional CI workflow covers Python 3.10 and 3.12 on Linux and Windows when adopted into a repository. It has not been pushed or run on GitHub in this task.

## v0.4.0 patient scenario lab (2026-11-09)

- Added pure synthetic patient scenario presets for asystole/VF cardiac arrest, respiratory arrest, airway restriction/occlusion, low heart rate and low oxygen-saturation targets, plus the original fault demo.
- Added independent simulated-patient JSON state to the dashboard API. Physical sensor feeds remain separate and cannot be changed by simulation controls.
- Added airway restriction, synthetic bag ventilation and synthetic CPR force controls. New tests include value validation, API authorization, scenario transitions and physical input ownership.
- **Local result:** 89 Python tests executed, 88 passed, one POSIX/serial optional test skipped; JavaScript syntax check passed; independent live HTTP smoke test passed. The benign `LOGGING FAILED` diagnostic printed in the suite is expected from an intentional logger-failure test.
- **Browser visual end-to-end test:** Not completed; this environment blocks Chromium from opening localhost (`ERR_BLOCKED_BY_ADMINISTRATOR`). The supplied Playwright script remains available to run in an unrestricted local browser environment.
- **Physical hardware and clinical behavior:** Not tested. All vital curves and restrictions are synthetic training illustrations, not neonatal physiology and not validated against a test lung or medical monitor.
