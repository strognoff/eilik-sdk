# Eilik SDK

Reusable Python SDK, CLI, packet monitor, and FastAPI controller service for an Eilik robot connected over USB serial. It is designed to run in WSL today and move unchanged to a Raspberry Pi later.

Protocol reference: <https://github.com/uDamocles/EilikSerialController>

## What This Implements

- Linux serial auto-detection, preferring `/dev/ttyACM0`
- Eilik VID:PID discovery fallback for `28e9:018a`
- Serial settings compatible with the reference implementation: `125000` baud, `timeout=1`, `rts=False`, `dtr=True`
- `HB1` handshake and keep-alive packet: `aa aa aa 0a 00 61 e4 c6 f1 ca 83 ff ad`
- Dynamic 5-byte session token extraction from the handshake reply
- Original servo command frame shape and checksum formula
- High-level `EilikController` methods for simple actions
- Packet logging to `logs/eilik.log`
- Monitor/sniffer mode for reverse engineering sensors and events
- FastAPI endpoints for local service control
- Unit tests for checksum, frame generation, and token parsing

## Install

```bash
cd /home/cechinel/.openclaw/workspace/eilik-sdk
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

If WSL USB passthrough is already active, the robot should appear as `/dev/ttyACM0` or as a USB CDC ACM serial device with VID:PID `28e9:018a`.

After `wsl --shutdown`, USB passthrough is dropped. From Windows PowerShell, reattach Eilik before running the SDK:

```powershell
usbipd list
usbipd attach --wsl --busid <BUSID>
```

For example, if `usbipd list` shows Eilik as bus `2-2`:

```powershell
usbipd attach --wsl --busid 2-2
```

If the device exists but is not readable/writable, add the WSL user to `dialout` or adjust a local udev rule:

```bash
sudo usermod -aG dialout "$USER"
```

Then restart the WSL shell/session so group membership refreshes.

## CLI

```bash
python cli.py connect
python cli.py wave
python cli.py nod
python cli.py shake_head
python cli.py look_left
python cli.py look_right
python cli.py reset
python cli.py monitor
```

Optional explicit serial port:

```bash
python cli.py wave --port /dev/ttyACM0
```

Monitor mode continuously reads incoming bytes, prints timestamped hex chunks, and saves them to `logs/eilik-monitor.log`:

```bash
python cli.py monitor
```

This is intended for later reverse engineering of touch sensors, tilt sensors, pickup detection, battery information, and emotion events.

## FastAPI Service

Start the service:

```bash
python cli.py serve --host 127.0.0.1 --port-http 8765
```

With an explicit serial device:

```bash
python cli.py serve --port /dev/ttyACM0 --host 127.0.0.1 --port-http 8765
```

Endpoints:

- `GET /`
- `GET /health`
- `GET /status`
- `POST /wave`
- `POST /nod`
- `POST /look_left`
- `POST /look_right`
- `POST /reset`

Example:

```bash
curl -X POST http://127.0.0.1:8765/wave
```

## Python SDK

```python
from eilik import EilikController

robot = EilikController()
robot.connect()
robot.wave()
robot.look_left()
robot.reset_pose()
robot.disconnect()
```

Available high-level methods:

- `connect()`
- `disconnect()`
- `wave()`
- `nod()`
- `shake_head()`
- `look_left()`
- `look_right()`
- `left_arm_up()`
- `left_arm_down()`
- `right_arm_up()`
- `right_arm_down()`
- `reset_pose()`

## Protocol Notes

The SDK preserves the packet format from `uDamocles/EilikSerialController`.

Handshake:

1. Send `HB1`: `aa aa aa 0a 00 61 e4 c6 f1 ca 83 ff ad`
2. Read the robot reply
3. Extract 5 bytes after `aa aa aa 0a 00 61`
4. Use that session token in servo frames

Servo frame:

```text
aa aa aa
14 00 61
<5-byte session token>
03 01
<motor id>
01
<position little-endian uint16>
00 00 00 00 00
<checksum>
```

Checksum:

```python
255 - (sum(payload_without_aa_header) % 256)
```

Motor map:

| Motor | ID | Low / Right | Center | High / Left |
|---|---:|---:|---:|---:|
| Right arm | 1 | 2500 | 1500 | 500 |
| Left arm | 2 | 500 | 1500 | 2500 |
| Torso | 3 | 500 | 1500 | 2500 |
| Head | 4 | 2500 | 1500 | 500 |

The known public protocol exposes horizontal head and torso axes plus arms. `nod()` is therefore implemented as a small expressive body/head gesture, not a true vertical neck nod.

## Architecture

```mermaid
flowchart TD
    CLI[cli.py / eilik.cli] --> Controller[EilikController]
    API[FastAPI service] --> Controller
    Controller --> Protocol[protocol.py]
    Controller --> Motions[motions.py]
    Controller --> Logger[logger.py]
    Controller --> Serial[/dev/ttyACM0 or discovered CDC ACM device]
    Serial --> Eilik[Eilik robot]
    Logger --> PacketLog[logs/eilik.log]
    Controller --> Monitor[monitor mode]
    Monitor --> MonitorLog[logs/eilik-monitor.log]
```

## Tests

```bash
pytest
```

Tests cover:

- Checksum generation
- Servo packet generation
- Session token parsing

## Files

```text
eilik/
  controller.py
  protocol.py
  motions.py
  logger.py
  cli.py
  service.py
cli.py
tests/
README.md
```
