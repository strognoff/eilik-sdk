# Eilik SDK

Reusable Python SDK, CLI, packet monitor, and FastAPI controller service for an Eilik robot connected over USB serial. It is designed to run in WSL today and move unchanged to a Raspberry Pi later.

This has nothing to do with Energize Lab, there is no official support.

Protocol reference: <https://github.com/uDamocles/EilikSerialController>

## What This Implements

- Linux serial auto-detection, preferring `/dev/ttyACM0`
- Eilik VID:PID discovery fallback for `28e9:018a`
- Serial settings compatible with the reference implementation: `125000` baud, `timeout=1`, `rts=False`, `dtr=True`
- `HB1` handshake and keep-alive packet: `aa aa aa 0a 00 61 e4 c6 f1 ca 83 ff ad`
- Dynamic 5-byte session token extraction from the handshake reply
- Captured official-app status handshake fallback: `aa aa aa 04 00 01 fa`
- Original servo command frame shape and checksum formula
- High-level `EilikController` methods for simple actions
- Bounded rotating API/packet logging to `logs/eilik.log`
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

# Display commands (decoded from EnergizeLab.exe reverse engineering)
python cli.py read_display --output face.bin
python cli.py write_display --image face.bin
python cli.py write_display --image face.png        # auto-resize any PNG to 128x64
python cli.py display_image --image face.png --invert
python cli.py read_servo_angles
python cli.py read_running_number
python cli.py write_running_number --index 1

# Stage 2: high-level actions, ambient, choreography, events
python cli.py list_actions
python cli.py action --name heart_eyes
python cli.py ambient --ambient clock --text 23:25 --hold 3
python cli.py ambient --ambient streak --text 7 --hold 2
python cli.py ambient --ambient pr --text 42=quinn --hold 2
python cli.py ambient --ambient energy_meter --text 87 --hold 2
python cli.py ambient --ambient crypto --text BTC=5.2 --hold 2
python cli.py ambient --ambient tts --text "hello there"
python cli.py choreo --name '[{"action": "hi_jeff"}, {"wait": 1}, {"motion": "wave"}]'
python cli.py morning
python cli.py welcome
python cli.py cron_done --name "morning brief"
python cli.py error --name "sync failed"
python cli.py subagent_done --name "Quinn"
python cli.py email --name "jeff"
python cli.py quinn
```

Optional explicit serial port:

```bash
python cli.py wave --port /dev/ttyACM0
```

Monitor mode continuously reads incoming bytes, prints timestamped hex chunks, and saves them to `logs/eilik-monitor.log`:

```bash
python cli.py monitor
```

## FastAPI Service

Start the local HTTP API:

```bash
python cli.py serve --host 127.0.0.1 --port-http 8765
```

With an explicit serial device:

```bash
python cli.py serve --port /dev/ttyACM0 --host 127.0.0.1 --port-http 8765
```

The service uses an **on-demand serial model**: it does not connect to Eilik at
startup, and it does not keep a background keepalive loop running. Each command
opens the serial session, runs the action, then disconnects so Eilik's firmware
can return to its normal autonomous/playful behavior.

### Motion endpoints

- `GET /`
- `GET /health` — service health only; does not open the serial device
- `GET /status` — alias for `/health`; `connected=false` is expected between commands
- `GET /motions` — list every available motion and motor name
- `POST /wave`
- `POST /nod`
- `POST /shake_head`
- `POST /look_left`
- `POST /look_right`
- `POST /left_arm_up`
- `POST /left_arm_down`
- `POST /right_arm_up`
- `POST /right_arm_down`
- `POST /reset`
- `POST /motion/{name}` — run any named motion from `/motions`
- `POST /servo/move` — direct motor position, e.g. `{"motor": "right_arm", "position": 500}`
- `GET /servo/angles` — read live servo positions

### Display endpoints

- `POST /display/image` — push a PNG (base64-encoded) to Eilik's screen
- `POST /display/raw` — push a raw 1024-byte framebuffer to Eilik's screen
- `POST /display/text` — render text (via Pillow) and push to Eilik's screen
- `POST /display/idle` — restore the known calm idle-eye face
- `POST /display/release` — diagnostic-only user-display release; on current firmware this may redraw the static wave/status icon

`/display/text` and `/display/image` default to `auto_idle=false`. That means
the API does not silently write the captured half-eye idle face after a custom
display. Pass `auto_idle=true` only when that cleanup is explicitly wanted.

### Routines

- `POST /routine/display_text_arms` — one on-demand serial session that writes text, moves both arms up/down for `duration_seconds`, then applies the requested cleanup
- `POST /test/display-text-arms` — alias for curl experiments

Cleanup options:

- `disconnect_only` — default; sends no cleanup commands after the routine
- `arms_down` — finishes with both arms down
- `arms_rest` — finishes with both arms at `1500`
- `reset_pose` — runs the SDK reset pose
- `idle_face` — writes the captured idle face; use only when explicitly wanted

### Stage 2: actions / ambient / events

- `POST /action {name, hold_seconds, auto_idle}` — run any of 58 actions
- `GET /actions` — list all actions
- `POST /ambient/clock {hour, minute, hold_seconds}` — live clock face
- `POST /ambient/streak {days}` — "Day N" streak face
- `POST /ambient/weather {condition}` — uppercase condition face
- `POST /ambient/pr {pr_number, author}` — "PR#N by Author"
- `POST /ambient/calendar {minutes_until, meeting_title}` — "@Nmin Title"
- `POST /ambient/energy {soi_percent}` — "SoI: NN%"
- `POST /ambient/mood {mood}` — mood word face
- `POST /ambient/crypto {ticker, change_pct}` — "BTC +5%↑"
- `POST /ambient/tts {text}` — long text face (auto-splits)
- `POST /morning` — run morning routine
- `POST /welcome` — wave + bow + "Welcome!"
- `POST /event/cron_done {name}` — ✓ + name
- `POST /event/error {message}` — X + message
- `POST /event/subagent_returned {name}` — got_it + name
- `POST /event/email {sender}` — @ + sender
- `POST /event/quinn` — "Quinn!" + wave
- `POST /event/crypto_pumped {ticker, pct}` — crypto ticker face
- `POST /choreo {steps: [...]}` — run a step-by-step routine

### Logs

- `GET /logs/recent?lines=120` — inspect recent API and packet logs

The log file is bounded by rotation so it cannot grow forever:

- `EILIK_LOG_PATH` defaults to `logs/eilik.log`
- `EILIK_LOG_MAX_BYTES` defaults to `1000000`
- `EILIK_LOG_BACKUP_COUNT` defaults to `5`

Examples:

```bash
# Show "Hello" on Eilik's face
curl -X POST http://127.0.0.1:8765/display/text \
  -H 'Content-Type: application/json' \
  -d '{"text": "Hello", "font_size": 16, "hold_seconds": 5, "auto_idle": false}'

# Run the exact bridge test: text + both arms for 5 seconds, no hidden cleanup
curl -X POST http://127.0.0.1:8765/routine/display_text_arms \
  -H 'Content-Type: application/json' \
  -d '{"text": "Hello Alice!!", "duration_seconds": 5, "cleanup": "disconnect_only"}'

# Run a named motion
curl -X POST http://127.0.0.1:8765/motion/wave

# Move one motor directly
curl -X POST http://127.0.0.1:8765/servo/move \
  -H 'Content-Type: application/json' \
  -d '{"motor": "right_arm", "position": 500}'

# Inspect recent logs
curl 'http://127.0.0.1:8765/logs/recent?lines=80'

# Show an arbitrary PNG (base64-encoded)
curl -X POST http://127.0.0.1:8765/display/image \
  -H 'Content-Type: application/json' \
  -d "{\"png_b64\": \"$(base64 -w0 face.png)\", \"invert\": false}"

# Read live servo angles
curl http://127.0.0.1:8765/servo/angles

# Stage 2 examples
curl -X POST http://127.0.0.1:8765/action -H 'Content-Type: application/json' -d '{"name": "hi_jeff"}'
curl -X POST http://127.0.0.1:8765/ambient/clock -H 'Content-Type: application/json' -d '{"hour": 23, "minute": 25}'
curl -X POST http://127.0.0.1:8765/ambient/pr -H 'Content-Type: application/json' -d '{"pr_number": 42, "author": "quinn"}'
curl -X POST http://127.0.0.1:8765/event/cron_done -H 'Content-Type: application/json' -d '{"name": "morning"}'
curl -X POST http://127.0.0.1:8765/morning -H 'Content-Type: application/json' -d '{}'
```

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
- `move_motor(motor_id, position)` — direct `cmd=0xA2` via canonical `format_data()`
- `read_servo_angles()` — returns live servo positions
- `read_display()` — returns 1024-byte framebuffer
- `write_display(image_1024b)` — push raw framebuffer
- `display_image(png_path, invert=False, threshold=128)` — push any PNG

### High-level actions (58 total)

Every action combines a face flash + a motion. List via `python -m eilik.cli list_actions`. Examples:

```python
robot.action("message")       # wave + "Message!! :)"
robot.action("good_morning")  # wave + "Morning! :)"
robot.action("heart_eyes")    # heart hands + "♥_♥"
robot.action("thinking")      # peek + "..."
robot.action("status_done")   # thumbs up + "DONE"
robot.action("trivia_correct")# thumbs up + "YES!"
```

### Ambient displays (live data on face)

```python
robot.show_clock(hour=23, minute=25)        # HH:MM clock
robot.show_streak(days=7)                   # "Day 7"
robot.show_weather("sun")                   # uppercase condition
robot.show_pr(42, author="quinn")           # PR notification
robot.show_calendar_nudge(5, "Catchup")     # "@5min Catchup"
robot.show_energy_meter(87)                 # "SoI: 87%"
robot.show_mood("happy")                    # mood face
robot.show_crypto_ticker("BTC", 5.2)        # "BTC +5%↑"
robot.show_tts_text("hello there")          # long text face
```

### Compound actions / event bridges

```python
robot.morning_routine()                     # greeting + energy + weather + wave
robot.task_completed()                      # status_done + thumbs up
robot.task_failed()                         # frustrated + "sorry"
robot.thinking_handoff()                    # "..." + peek
robot.subagent_returned("Quinn")            # got_it + Quinn!
robot.cron_tick_done("morning brief")       # ✓ + cron name
robot.error_flash("sync failed")            # X + error message
robot.email_arrived("jeff")                 # @ + sender
robot.pr_alert(42, "quinn")                 # PR notification
robot.quinn_comms()                         # "Quinn!" + wave
robot.crypto_pumped("BTC", 5.0)             # crypto ticker face
robot.welcome_back()                        # bow + wave
```

### Choreography DSL

```python
robot.choreography([
    {"action": "good_morning"},
    {"ambient": "clock", "text": "07:30"},
    {"ambient": "energy_meter", "soi_percent": 87},
    {"ambient": "weather", "condition": "sun"},
    {"wait": 1.0},
    {"motion": "wave"},
], inter_step_delay=0.3)
```

Step types: `action`, `motion`, `ambient`, `text`, `face`, `wait`.

Display demo:

```python
from eilik import EilikController

robot = EilikController()
robot.connect()
robot.display_image("smile.png", invert=False)  # show on screen
robot.wave()
robot.disconnect()
```

## Wiring Crons to Eilik

Two scripts make cron → Eilik integration trivial:

### `scripts/ensure_eilik_service.sh` — keep the HTTP API available

Pings `/health`. If unreachable, kills the leftover uvicorn process,
auto-detects the Eilik USB port (`/dev/ttyACM1` or wherever `28e9:018a`
shows up), and restarts the FastAPI service. This keeps the HTTP API
available, but the API itself still uses short-lived serial sessions and does
not hold Eilik in USB control mode. Silent when healthy, logs
to `/tmp/eilik-service.watchdog.log` on restart attempts.

Suggested cron: every 5 minutes (`*/5 * * * *`).

### `scripts/run_with_eilik.sh` — generic wrapper (in `openclaw-automation-scripts`)

```bash
# Usage: run_with_eilik.sh <cron-name> <command...>
run_with_eilik.sh morning-brief python3 scripts/morning_briefing.py
run_with_eilik.sh garmin-sync .venv/bin/python scripts/garmin_sync.py --latest
```

Wraps any command. On exit code:

- `rc == 0` → `POST /event/cron_done` with `{"name": "<cron-name>"}`
- `rc != 0` → `POST /event/error` with `{"message": "<cron-name> failed (rc=N)"}`

The curl is best-effort (`--max-time 30`, never blocks the script). The
wrapper always exits with the wrapped command's exit code so the cron
scheduler still reports success/failure correctly. Override the target
with `EILIK_URL=http://127.0.0.1:8765`.

### Wired crons

- Calendar calcurse sync — `cron_done("calcurse-sync")`
- Garmin daily sync — `cron_done("garmin-sync")`
- Morning news brief — `cron_done("morning-brief")`
- Nova Medium→LinkedIn — `cron_done("medium-linkedin")`
- Nova system healthcheck — `cron_done("nova-healthcheck")`
- Nova daily day summary (multi-step) — `cron_done("day-summary")` via prompt-side curl

## Protocol Notes

The SDK uses the canonical `format_data()` packet format from
`PackAnalyData.py` in the official `EnergizeLab.exe` (recovered via PyInstaller
extraction + xdis byte-code disassembly). See
[`reversing/_reports/energizelab_windows_app.md`](reversing/_reports/energizelab_windows_app.md).

Packet format:

```
aa aa aa <length:u16-LE> <cmd> <payload> <checksum>
```

Where:
- `length = len(payload) + 3` (covers length byte + cmd + checksum)
- `checksum = (~sum(length_bytes + cmd + payload)) & 0xFF`

Commands recovered from `EnergizeLab.exe`:

| Cmd  | Purpose                           |
|------|-----------------------------------|
| 0x01 | Ping / MCU info                   |
| 0x02 | Confirm upgrade                   |
| 0x03 | Content update                    |
| 0x04 | Firmware flash                    |
| 0x05 | Firmware flash (direct)           |
| 0x20 | Read all (2 KB)                   |
| 0x21 | Read single                       |
| 0x31 | Write specified                   |
| 0x41 | Reinit SD                         |
| 0x42 | Format SD                         |
| 0xA1 | Read servo angles                 |
| 0xA2 | Write servo angles (motion)       |
| 0xA3 | Read display (1024 bytes)         |
| 0xA4 | Write display (1024 bytes)        |
| 0xA5 | Read running number (animation)   |
| 0xA6 | Write running number              |

The display is **128×64 1bpp monochrome SSD1306 page-mode**, 8 pages × 128 columns × LSB-first within each byte. `read_display` and `write_display` are wired into the controller + CLI + FastAPI.

If the robot opens over `/dev/ttyACM0` but does not reply to the public `HB1` handshake, the SDK falls back to the official-app status request captured from `captures/eilik-official.pcapng`:

```text
aa aa aa 04 00 01 fa
```

The captured official-app connect sequence was:

1. `cmd=01` status request: `aa aa aa 04 00 01 fa`
2. Robot `cmd=01` status reply with device/version-looking data
3. `cmd=20` mode/index request: `aa aa aa 04 00 20 db`
4. `cmd=02` session/index start: `aa aa aa 09 00 02 00 09 00 00 00 eb`
5. Robot re-enumerates, acknowledges `cmd=02`, then the app sends many `cmd=03` action/resource path frames such as `a/0/01/00/01`

After the official app performed this sequence, the robot began replying to the legacy `HB1` token handshake again, and SDK `wave` / `nod` commands succeeded over `/dev/ttyACM0`. The likely behavior is that the official app wakes or switches Eilik into the serial command mode expected by the public reference implementation. The captured official frames are still useful as a fallback/status probe and for future protocol work. See [docs/CAPTURE_HANDSHAKE.md](docs/CAPTURE_HANDSHAKE.md).

Legacy `HB1` handshake:

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
