# SAMD21 synthetic node example

This project compiles a real, nonblocking-loop **mock IMU** node. It does not access IMU registers, I2C, SPI or actuator pins. The build target follows the pressure repository's compiler variant; confirm the physical target before uploading.

Build from the package root:

```sh
python -m platformio run -d firmware/node_example
```

With this example on a separate compatible board:

```sh
python -m kevin --mode mixed --example-port head_node=COM4
```

The host sends `SESSION <random-id>` on opening the port. A node boot without a session repeatedly emits `# SESSION_REQUIRED`; the explicit example-mode serial adapter responds. The node emits hello, then timestamped synthetic quaternion measurements at about 10 Hz and a heartbeat every second. The session is host-assigned and is not a persistent hardware boot counter. A new host/connection assigns a new one; no claim of authenticated identity is made.

The transmitter keeps one bounded pending frame and drains it according to USB write capacity. If it is busy, the next poll waits instead of allocating an unbounded queue. Commands use a bounded line buffer; oversized commands are dropped. A new session command waits for the previous complete output line before emitting the new hello.

`SensorDriver`, `MockImu`, `UnavailableImu`, `Sample` and `Transport` are reusable interfaces/examples. Replace the mock with a validated driver after confirming hardware. `UnavailableImu` produces explicit invalid data while a real driver is unavailable; it never fabricates a valid orientation.

The serializer is a bounded, allocation-free JSON writer for hello/heartbeat/measurement. Calibration/status transition logic belongs in each real driver. There is no MCU CAN driver here. The pressure project's source in the neighboring folder is untouched and should remain the pressure-board firmware.

For native checks, the Python test suite compiles `test_native/test_node.cpp` when `g++` is available, executes its assertions and feeds its actual stdout messages into the Python decoder/manager.
