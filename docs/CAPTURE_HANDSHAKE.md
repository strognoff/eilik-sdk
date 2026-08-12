# Capturing the Real Eilik Handshake

The public reference implementation uses this first packet:

```text
aa aa aa 0a 00 61 e4 c6 f1 ca 83 ff ad
```

On the current WSL setup, Linux permissions and USB passthrough work, and the SDK can open `/dev/ttyACM0`, but this Eilik firmware does not reply to that `HB1` packet.

## Findings From `captures/eilik-official.pcapng`

The official app capture shows a different command family:

```text
OUT aa aa aa 04 00 01 fa
IN  aa aa aa 26 00 01 ...
OUT aa aa aa 04 00 20 db
OUT aa aa aa 09 00 02 00 09 00 00 00 eb
IN  aa aa aa 04 00 02 f9
OUT aa aa aa 1c 00 03 ... 61 2f ...   # repeated action/resource paths
IN  aa aa aa 06 00 03 01 01 f4        # repeated cmd=03 ack
```

This capture has 1,435 `aa aa aa` frames. It includes the official connect/status flow and the app syncing hundreds of `cmd=03` action/resource path frames like `a/0/01/00/01`, but it does not include an obvious direct servo or movement command. The SDK now uses the captured `cmd=01` status request as a safe connection fallback when `HB1` is silent.

After this official-app sequence ran once, the robot began replying to the public `HB1` packet again:

```text
OUT aa aa aa 0a 00 61 e4 c6 f1 ca 83 ff ad
IN  aa aa aa 0a 00 61 <5-byte token> ff <checksum>
```

With that token path active, SDK `wave` and `nod` commands succeeded over `/dev/ttyACM0`.

## Why Capture Is Needed

For the legacy `HB1` protocol, the five-byte session token is dynamic, so replaying an old captured movement packet is not enough. We need the exchange that creates the session:

1. Host sends one or more init packets.
2. Robot replies with a token-bearing frame.
3. Host injects that token into motion commands.

For this firmware's official protocol variant, the next useful capture would include one clear action such as wave, nod, calibration, or a single RobotStudio motion. Without that, the captured official frames only prove connection/index sync, not direct motor control. For now, the working control path is: run the official app once if needed, then use the legacy token commands.

## Windows USBPcap / Wireshark Path

Use this when the official Windows app or updater can talk to Eilik.

1. Detach Eilik from WSL so Windows owns the device:

   ```powershell
   usbipd detach --busid 2-2
   usbipd list
   ```

   The Eilik row should no longer say `Attached`.

2. Install Wireshark with USBPcap enabled.

3. Start a USBPcap capture for the controller that contains Eilik.

4. Run the official Eilik app or updater.

5. Do a small, easy-to-identify action:

   - connect/open the robot
   - trigger one movement or calibration action
   - wait 2-3 seconds

6. Stop capture and save as:

   ```text
   eilik-official.pcapng
   ```

7. Put the capture in this repo, preferably:

   ```text
   captures/eilik-official.pcapng
   ```

   Captures are gitignored because they may contain device serials or unrelated USB traffic.

8. Extract likely Eilik frames:

   ```bash
   python tools/extract_usb_frames.py captures/eilik-official.pcapng --all
   python tools/extract_usb_frames.py captures/eilik-official.pcapng --contains "aa aa aa"
   ```

## What To Look For

Useful signs:

- OUT packets from host to Eilik shortly after app connect
- IN packets from Eilik immediately after an OUT packet
- frames beginning with `aa aa aa`
- frames containing `0a 00 61` or `14 00 61`
- repeated keep-alive-like packets every ~2 seconds
- a short IN frame where five bytes after a stable signature change between sessions

## After Capture

Once we have the real exchange, update:

- `eilik/protocol.py` for new handshake constants/parsing
- `eilik/controller.py` for any multi-step init flow
- `tests/test_protocol.py` with captured-but-redacted frame fixtures

Then retry:

```bash
python cli.py connect
python cli.py wave
```
