# Eilik HTTP API

The HTTP API is the bridge for controlling Eilik. Keep the service running, then call it with curl, Python, OpenClaw, or any local tool.

Base URL:

```bash
export EILIK_URL=http://127.0.0.1:8765
```

The service uses an on-demand serial model. Each command opens Eilik, runs the action, then disconnects. Between commands, `/health` should report `connected=false`.

## Health And Discovery

```bash
curl "$EILIK_URL/health"
curl "$EILIK_URL/status"
curl "$EILIK_URL/motions"
curl "$EILIK_URL/actions"
curl "$EILIK_URL/logs/recent?lines=120"
```

OpenAPI spec:

```bash
curl "$EILIK_URL/openapi.json"
```

A generated copy is checked in at [openapi.json](openapi.json).

## Webapp

Full setup guide:

- [WEBAPP.md](WEBAPP.md)

Open the local control webapp:

```bash
xdg-open "$EILIK_URL/app"
```

Open the kids game sequence builder:

```bash
xdg-open "$EILIK_URL/app/game"
```

Or browse to:

```text
http://127.0.0.1:8765/app
```

The webapp calls this API directly. Loading it is read-only: it checks health,
loads available motions, and reads recent logs. Eilik only moves or changes
screen when a command button is pressed. The kids game sends a whole playlist
to `/routine/sequence`.

## Display

Show text for 5 seconds without hidden cleanup:

```bash
curl -X POST "$EILIK_URL/display/text" \
  -H 'Content-Type: application/json' \
  -d '{"text":"Hello Alice!!","font_size":16,"hold_seconds":5,"auto_idle":false}'
```

Show text and then explicitly restore the captured idle face:

```bash
curl -X POST "$EILIK_URL/display/text" \
  -H 'Content-Type: application/json' \
  -d '{"text":"Done","hold_seconds":2,"auto_idle":true}'
```

Send a PNG:

```bash
curl -X POST "$EILIK_URL/display/image" \
  -H 'Content-Type: application/json' \
  -d "{\"png_b64\":\"$(base64 -w0 face.png)\",\"invert\":false,\"hold_seconds\":3,\"auto_idle\":false}"
```

Send a raw 1024-byte framebuffer as hex:

```bash
curl -X POST "$EILIK_URL/display/raw" \
  -H 'Content-Type: application/json' \
  -d '{"framebuffer_hex":"<2048 hex chars>"}'
```

Known display caveat:

- `auto_idle=false` is the default for custom display writes.
- `auto_idle=true` writes the captured idle-eye face after the hold.
- `/display/release` is diagnostic only. On current firmware it can redraw the turquoise control/status icon.

## Motion

Named motions:

```bash
curl -X POST "$EILIK_URL/motion/wave"
curl -X POST "$EILIK_URL/motion/nod"
curl -X POST "$EILIK_URL/motion/shake_head"
curl -X POST "$EILIK_URL/motion/wiggle"
curl -X POST "$EILIK_URL/motion/reset_pose"
```

Named motions use the canonical direct servo packet path (`cmd=0xA2`), the same
path as `/servo/move`.

Shortcut endpoints:

```bash
curl -X POST "$EILIK_URL/wave"
curl -X POST "$EILIK_URL/nod"
curl -X POST "$EILIK_URL/look_left"
curl -X POST "$EILIK_URL/look_right"
curl -X POST "$EILIK_URL/reset"
curl -X POST "$EILIK_URL/left_arm_up"
curl -X POST "$EILIK_URL/left_arm_down"
curl -X POST "$EILIK_URL/right_arm_up"
curl -X POST "$EILIK_URL/right_arm_down"
```

Direct servo move:

```bash
curl -X POST "$EILIK_URL/servo/move" \
  -H 'Content-Type: application/json' \
  -d '{"motor":"right_arm","position":500}'
```

Motor names:

- `right_arm`
- `left_arm`
- `torso`
- `head`

Position range:

- `0` to `3000`
- `1500` is center/rest

Read live servo angles:

```bash
curl "$EILIK_URL/servo/angles"
```

## Composed Routines

Text plus both arms for 5 seconds, no hidden cleanup:

```bash
curl -X POST "$EILIK_URL/routine/display_text_arms" \
  -H 'Content-Type: application/json' \
  -d '{"text":"Hello Alice!!","duration_seconds":5,"cleanup":"disconnect_only"}'
```

Same routine, finish with arms down:

```bash
curl -X POST "$EILIK_URL/routine/display_text_arms" \
  -H 'Content-Type: application/json' \
  -d '{"text":"Hello Alice!!","duration_seconds":5,"cleanup":"arms_down"}'
```

Cleanup options:

- `disconnect_only`: sends no cleanup command after the routine.
- `arms_down`: finishes with right arm down and left arm down.
- `arms_rest`: finishes both arms at `1500`.
- `reset_pose`: runs the SDK reset pose.
- `idle_face`: writes the captured idle face.

Alias for quick experiments:

```bash
curl -X POST "$EILIK_URL/test/display-text-arms" \
  -H 'Content-Type: application/json' \
  -d '{"text":"Hello Alice!!","duration_seconds":5,"cleanup":"disconnect_only"}'
```

Kids game sequence API:

```bash
curl -X POST "$EILIK_URL/routine/sequence" \
  -H 'Content-Type: application/json' \
  -d '{
    "steps": [
      {"type":"display_text","text":"Hello Alice!!","hold_seconds":1.5},
      {"type":"motion","motion":"wave"},
      {"type":"wait","seconds":0.5},
      {"type":"motion","motion":"thumbs_up"}
    ],
    "cleanup":"disconnect_only",
    "step_pause_seconds":0.2
  }'
```

Supported sequence block types:

- `display_text`: `text`, optional `hold_seconds`, optional `font_size`.
- `motion`: `motion` from `GET /motions`.
- `wait`: `seconds`.

## High-Level Actions

List actions:

```bash
curl "$EILIK_URL/actions"
```

Run an action:

```bash
curl -X POST "$EILIK_URL/action" \
  -H 'Content-Type: application/json' \
  -d '{"name":"hi_jeff","hold_seconds":1.5,"auto_idle":false}'
```

Useful action names include:

- `hi_jeff`
- `good_morning`
- `got_it`
- `done`
- `happy`
- `thinking`
- `status_done`
- `status_error`

## Ambient And Event Bridges

```bash
curl -X POST "$EILIK_URL/ambient/clock" \
  -H 'Content-Type: application/json' \
  -d '{"hour":12,"minute":30,"hold_seconds":3}'

curl -X POST "$EILIK_URL/ambient/weather" \
  -H 'Content-Type: application/json' \
  -d '{"condition":"sun","hold_seconds":3}'

curl -X POST "$EILIK_URL/ambient/pr" \
  -H 'Content-Type: application/json' \
  -d '{"pr_number":42,"author":"quinn"}'

curl -X POST "$EILIK_URL/event/cron_done" \
  -H 'Content-Type: application/json' \
  -d '{"name":"morning"}'

curl -X POST "$EILIK_URL/event/error" \
  -H 'Content-Type: application/json' \
  -d '{"message":"sync failed"}'
```

## Logs

Recent logs:

```bash
curl "$EILIK_URL/logs/recent?lines=80"
```

The service logs API and packet events to `logs/eilik.log`, with rotation:

- `EILIK_LOG_MAX_BYTES`: default `1000000`
- `EILIK_LOG_BACKUP_COUNT`: default `5`

A useful debugging pattern:

```bash
curl -X POST "$EILIK_URL/routine/display_text_arms" \
  -H 'Content-Type: application/json' \
  -d '{"text":"Test","duration_seconds":2,"cleanup":"disconnect_only"}'

curl "$EILIK_URL/logs/recent?lines=120"
```
