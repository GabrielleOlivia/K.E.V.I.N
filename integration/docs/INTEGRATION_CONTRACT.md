# Teammate integration contract

## What every module must deliver

| Deliverable from module developer | Acceptance by integration owner |
|---|---|
| Exact board, IC markings and revision | Identity recorded; schematic/datasheet match checked |
| Wiring, supply and bus configuration | Reviewed against actual board; no pin changes inferred from a similarly named board |
| Driver source and build configuration | Reproducible compile; initialization failure is visible |
| Node ID and sensor ID(s) | Agreed registry entries, unique ownership |
| Measurement type, unit, shape and range | Documented engineering meaning; registry validation passes |
| Sampling/report rate, timestamp semantics | Timeouts and link budget agreed; acquisition vs send time distinguished |
| Calibration procedure/state | Uncalibrated/failed samples are flagged; physical reference documented |
| Error codes and recovery | Invalid outputs null, fault path tested, reinitialization bounded |
| Protocol examples and a recorded log | Hello, valid/invalid sample, heartbeat, fault, recovery and reboot examples |
| Tests and evidence | Host tests plus hardware test conditions; never label software mocks as bench results |

A sensor module can attach locally through I2C/SPI/ADC, to a node over another local interface, or behind a future gateway. Only the normalized message contract crosses into the manager. The pressure module is the deliberate legacy exception handled by the CSV adapter.

## Integration owner procedure

1. Agree IDs and add a `SensorSpec` entry to `config/sensors.json`.
2. Decide which acquisition unit is authoritative. Do not send both counts and converted units under one measurement name; use separate registered channels if both are required.
3. Select the transport adapter. Native JSONL requires no sensor-specific Python code. A proprietary sensor output gets its own adapter under `kevin/adapters/`, with fixtures and tests.
4. Test decoder → registry → manager → state using the module's fixture data.
5. Assign a physical serial port with `--jsonl-port node_id=PORT`, or `--pressure-port PORT` for legacy pressure. Mixed mode automatically removes that node's sensors from simulation.
6. Verify unplug/reset/stall/invalid/calibration cases before using derived outputs.
7. Record the firmware version, registry settings, wiring revision and run log for each bench experiment.

`SensorManager.accept(Message_or_dict, source)` is the core API. `IntegrationService.receive_line(bytes, source, adapter=None)` is the normal ingress; it adds logging. `snapshot()` returns a coherent copy containing all known channels. Consumers must use `valid` and `value`, not `last_received_value`.

## C++ driver interface

`firmware/node_example/include/sensor.hpp` supplies:

- `begin()`: initialize without pretending success when the device is absent.
- `poll(now_ms, sample)`: return promptly; true means a new sample attempt is ready. Both successful and failed attempts produce a sample. Do not return a cached sample with a new timestamp.
- `requestCalibration()`: accept/reject a calibration request; real drivers must report progress/results through sample state. No automatic physical calibration is assumed.

`Sample` contains acquisition/read-completion time, ID/type/unit, scalar or quaternion data, validity, calibration state and error. `Transport` separates serialization from a physical connection. `MockImu` is executable synthetic acquisition; `UnavailableImu` is executable failure behavior for unspecified hardware. Replace the latter only after identifying the board. The example serializer supports hello, heartbeat and measurement; other node-wide control types are defined by the host contract and can be added when a module needs them.

Use nonblocking state machines for real conversions where feasible. A driver must have a maximum read/initialization deadline. Do not hold the host manager lock or block all MCU sensors waiting indefinitely for one device. The preserved pressure firmware retains its proven blocking conversion timing; altering it belongs in a separate, validated change.

## IMU requirements before writing its physical driver

The project name says **BMI360/BMM350**, while Bosch's documented smart IMU is **BHI360**. This is a naming warning, not proof of the chip fitted to your assembly. Confirm chip markings, PCB revision and the exact schematic. If it is BHI360, its firmware/fusion path differs from treating a conventional BMI-series IMU as raw registers. Do not reuse a guessed address or register map.

Agree all of the following: interface and voltage; reset/interrupt wiring; whether external sensor firmware must be uploaded; how BMM350 connects; enabled virtual/physical outputs; axis order and signs; quaternion convention; world/body transform direction; sensor mounting transform; timestamp resolution/wrap; calibration accuracy flags; and actual supported rate.

The common orientation value is `[w,x,y,z]`, a unit quaternion mapping the calibrated sensor/body frame into the agreed common world frame. The host checks norm within 0.98–1.02. `frame_id` and `mounting_calibrated` metadata must reflect an actually established convention. The geometry function returns relative **sensor rotation magnitude**, not a full anatomical neck-angle estimate. Physical fusion remains unavailable without time mappings and mounting/frame evidence.

Use the official [BHI360 product documentation](https://www.bosch-sensortec.com/en/products/smart-sensor-systems/bhi360) and [Bosch sensor APIs](https://www.bosch-sensortec.com/en/software-tools/software/drivers) only after identifying the fitted device.

## Example: add another temperature channel

Copy the existing temperature registry entry, assign a distinct `sensor_id` and the appropriate `node_id`, and keep `measurement=skin_temperature`, `unit=degC`, `shape=scalar`. The module emits hello and measurements matching those fields. Run physical mode with the updated registry. No temperature branch is needed in `manager.py`. To simulate the extra channel, explicitly add a generator entry; the simulator does not invent an unknown sensor model.

## Ownership and review boundary

Liv reviews the contract, registry, timestamp behavior, adapters, state transitions and integration evidence. Sensor developers review their own chip initialization, conversion formulas, calibration and read deadlines. Mechanical/physiological-model teammates supply interpretation and actuator logic as separate work. Dashboard developers consume state without changing validity or inventing missing values. Changes to wire semantics require a version decision and regression fixtures.
