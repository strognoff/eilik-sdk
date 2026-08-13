# Eilik Control Webapp

The webapp is a local browser control panel for Eilik. It is served by the same FastAPI process as the API and calls the API endpoints directly.

Local URL:

```text
http://127.0.0.1:8765/app
```

Loading the page is read-only. It calls `/health`, `/motions`, and `/logs/recent`; Eilik only moves or changes screen after pressing a command button.

## Setup

From the SDK checkout:

```bash
cd /home/cechinel/.openclaw/workspace/eilik-sdk
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

If Eilik is connected through WSL USB passthrough, make sure the device is attached:

```powershell
usbipd list
usbipd attach --wsl --busid <BUSID>
```

In this setup Eilik usually appears as `/dev/ttyACM0`.

Start the API and webapp:

```bash
python cli.py serve --port /dev/ttyACM0 --host 127.0.0.1 --port-http 8765
```

Or use the watchdog helper:

```bash
EILIK_PORT=/dev/ttyACM0 scripts/ensure_eilik_service.sh
```

Open the webapp:

```bash
xdg-open http://127.0.0.1:8765/app
```

Or paste this into a browser:

```text
http://127.0.0.1:8765/app
```

## What The Webapp Can Do

- Show API status.
- Link to FastAPI docs at `/docs`.
- Send text to Eilik's screen.
- Run the text plus both-arms routine.
- Trigger every movement returned by `/motions`.
- Move individual servos with sliders.
- Read servo angles.
- Show recent rotating logs from `/logs/recent`.
- Show the exact JSON response or error for each command.

## Useful API Checks

```bash
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/motions
curl 'http://127.0.0.1:8765/logs/recent?lines=80'
```

Between commands, `/health` should report:

```json
{
  "service": "ok",
  "mode": "on-demand",
  "connected": false,
  "port": "/dev/ttyACM0",
  "protocol": null
}
```

That is expected. The service should not keep the serial connection open while Eilik is idle/playful.

## Troubleshooting

If the webapp does not load:

```bash
curl -i http://127.0.0.1:8765/app
pgrep -af "eilik serve|uvicorn|python -u -m eilik"
```

If the API is down:

```bash
EILIK_PORT=/dev/ttyACM0 scripts/ensure_eilik_service.sh
curl http://127.0.0.1:8765/health
```

If commands fail because Eilik is not found:

```bash
ls -l /dev/ttyACM*
```

Then reattach USB from Windows PowerShell:

```powershell
usbipd list
usbipd attach --wsl --busid <BUSID>
```

If a movement or display command did something unexpected, inspect recent logs:

```bash
curl 'http://127.0.0.1:8765/logs/recent?lines=160'
```

The API logs rotate automatically:

- `EILIK_LOG_PATH`: default `logs/eilik.log`
- `EILIK_LOG_MAX_BYTES`: default `1000000`
- `EILIK_LOG_BACKUP_COUNT`: default `5`

