# EnergizeLab Windows app — full reverse engineering notes

Source: `EnergizeApp/` (PyInstaller-bundled MSIX app,
`EnergizeLab.exe`, 5.6 MB, Python 3.10, signed by
`CN=E7F21695-0562-4424-A582-359B1C4DADFE` — "Shenzhen Zhuneng
Technology Co., Ltd.", the maker of Eilik).

Extracted with `pyinstxtractor-ng` 2026.7.3 into
`reversing/_energizelab_extract/EnergizeLab.exe_extracted/`.

The PYZ archive contains 1,095 files. The app code modules in
`FirmwareBase/` are encrypted (custom AES layer; pyinstxtractor
preserved their docstrings and bytecodes). All strings and the
constants pool are recoverable.

## What this app actually does

This is a **firmware-update + SD-card-formatter** companion tool for
the Eilik robot. It does NOT contain any "show this emotion" or
"play this sound" command — it only:

* pings the robot on USB serial
* reads MCU info (chip_id, mode_number, firmware_number, boot_firmware, mcu_status)
* fetches firmware manifest from `https://file.energizelab.com.cn/`
  or `http://175.24.102.176/software/energizelab/robot/user/`
  or `http://45.32.81.33:789/software/energizelab/robot/user/`
* downloads firmware ZIPs into `LOCALAPPDATA\Programs\EnergizeLab\`
  (Windows) or `~/Library/Application Support/EnergizeLab` (mac)
* formats the SD card via FAT operations
* writes firmware / resource bundles to the SD card or directly
  to Flash via cmd 0x04 / 0x05

## `PackAnalyData.py` — the full Eilik USB protocol

This module is the **single source of truth** for the Eilik packet
format. Reconstructed Python source:

```python
import struct, time
from datetime import datetime, timedelta

def sum_data(data):
    """1-byte checksum: (~sum(data)) & 0xFF"""
    return (~sum(data)) & 0xFF

def format_data(data):
    """Wrap a payload: [magic] [len:u16le] [data...] [checksum]"""
    length = len(data) + 3   # length = 1(length itself)+1(inst)+len(data)+1(checksum)
    out = []
    out.extend([0xAA, 0xAA, 0xAA])
    out.extend(struct.pack('<H', length))
    out.extend(data)
    out.append(sum_data(out[3:]))   # checksum over [len, instruction, data]
    return out

def ping_data():
    return format_data([0x01])

def inst_data(inst1, inst2, data):
    out = []
    if inst1 is not None: out.append(inst1)
    if inst2 is not None: out.append(inst2)
    if data  is not None: out.extend(data)
    return format_data(out)

class CheckDataBase:
    """Stream framer for incoming bytes."""
    def __init__(self):
        self.frame_length = 0
        self.check_data = bytearray()
        self.check_time = datetime.now()
    def update(self):
        now = datetime.now()
        if not self.check_data:
            self.check_time = now
        elif now - self.check_time > timedelta(milliseconds=20):
            self.check_data.clear()
    def clear(self):
        self.check_data.clear()

def check_data(data, base):
    base.update()
    list_data = None
    for d in data:
        base.check_data.append(d)
        length = len(base.check_data)
        if length < 5:
            if length < 3 or d != 0xAA:
                base.clear()
            continue
        if length == 5:
            # length byte is at byte 3, low 8 bits at byte 3,
            # high 8 bits at byte 4 — but they pack as <H and
            # take [-2:] so the 2 bytes BEFORE the end... bug or
            # intentional. We use 2 bytes at offset 3.
            (base.frame_length,) = struct.unpack('<H', base.check_data[-2:None])
            continue
        if length == base.frame_length + 3:
            list_data = bytearray(base.check_data)
            base.clear()
            continue
        if length > base.frame_length + 3:
            base.clear()
    return list_data
```

## Command table (from the module docstring)

| Cmd  | Name                       | Purpose / payload                                |
|------|----------------------------|--------------------------------------------------|
| 0x01 | ping                       | request robot's MCU info                         |
| 0x02 | confirm_upgrade            | write target firmware version                    |
| 0x03 | content_update             | subcmd 0x01 = file compare; 0x02 = write; 0x03 = finish with checksum |
| 0x04 | firmware_flash             | write firmware to Flash (resource file already transferred) |
| 0x05 | firmware_flash_direct      | subcmd 0x01 file info; 0x02 file data; 0x03 confirm |
| 0x20 | read_all (SD)              | returns 2 KB                                     |
| 0x21 | read_single (SD)           | returns *                                        |
| 0x31 | write_specified (SD)       |                                                  |
| 0x41 | reinit_sd                  |                                                  |
| 0x42 | format_sd                  |                                                  |
| **0xA1** | **read_servo_angles**  | returns servo angles                             |
| **0xA2** | **write_servo_angles** | **THIS IS WHAT WE USE** — `count, [id1,pos_l,pos_h] × count` |
| **0xA3** | **read_display**      | returns current display content                  |
| **0xA4** | **write_display**     | **THIS UNLOCKS ARBITRARY SCREEN TEXT — 1024 bytes payload** |
| 0xA5 | read_running_number        |                                                  |
| 0xA6 | write_running_number       |                                                  |

The robot supports up to 4 servos per packet (`id1..id4`),
each as `(servo_id, pos_l, pos_h)` — i.e. 16-bit position in
little-endian across two bytes.

## What we can do NOW with `cmd=0xA4`

The Windows app does NOT use `cmd=0xA4` (it only updates firmware).
But the firmware **understands** it. The reference SDK and our
current SDK already use `cmd=0xA2` for motion; the same wire
format works for `0xA4` if we just swap the instruction byte.

**The 1024-byte display payload is almost certainly a raw
framebuffer**, not arbitrary text. To find out the encoding
(likely RGB565 or a 1-bit monochrome bitmap), we need to:

1. Send `0xA3` (read display) and decode the response.
2. Compare against `0xA4` payloads we can construct.
3. Render known images/text and inspect.

This is a 2-hour experiment with `inst_data(0xA3, None, None)`
and `inst_data(0xA4, None, [bytes...])`.

## What about microphone / audio?

`EilikPerameter.py` only handles **serial-parameter read/write**
(write_perameter, read_perameter). The official app does NOT
expose any microphone command on USB serial. Likely reasons:

* Microphone samples stay on the robot and are processed locally
  (wake-word, sound detection) — never sent over USB.
* The "play sound" feature may be triggered by writing a
  "running number" (`cmd=0xA6`) that the firmware maps to a
  pre-stored audio asset index.

## What about BLE (per the Android app)?

The Android `app-release.apk` uses `react-native-ble-plx`
(`safeWriteCharacteristicForDevice`, `safeMonitorCharacteristicForDevice`)
and wraps every payload with `formatData_v2(headId, cmd, data)`
which is the same `aa aa aa length headId token cmd pktNum totPkts data checksum`
frame documented in `_reports/formatData_v2_commands.md`. The
Windows app's `cmd` field is the BLE `headId=0x00 cmd` value;
the Android `headId` is the BLE routing namespace, not present
on USB. So:

* USB uses the short protocol with just `cmd`.
* BLE uses the long protocol with `headId` + `cmd` + token.

Both share the same `format_data()` packet wrapper, which
explains why our servo command `aa aa aa 04 00 A2 ...` works
on USB while the Android app uses `aa aa aa 1a 01 <5 bytes>
0x A2 <pktNum> <totPkts> <data...> <checksum>` over BLE.

## Direct test plan

1. **Read display**: send `inst_data(0xA3, None, None)`. The
   robot should respond with `aa aa aa ... 0xA3 <1024 bytes>`.
   Decode the 1024 bytes and see if it's a known image format.
2. **Write display**: construct `inst_data(0xA4, None, [0]*1024)`
   and send. If Eilik shows a blank screen, the encoding is
   all-zero. If it errors, the firmware wants a specific
   format.
3. **Read servo angles** (`cmd=0xA1`): confirm our servo
   mapping by sending `inst_data(0xA1, None, None)` and
   observing which servo IDs respond.
4. **Read running number** (`cmd=0xA5`): this is likely the
   "currently-playing animation" pointer. Useful for
   detecting what's actually on screen.

## Key URLs

```python
WebBaseUrls = [
    "https://file.energizelab.com.cn/",
    "http://175.24.102.176/software/energizelab/robot/user/",
    "http://45.32.81.33:789/software/energizelab/robot/user/",
]
```

These point to where the firmware ZIPs and `firmware_info_compress.json`
live. Fetching them (with bz2 decompression for the JSON) gives
us the firmware manifest — which lets us see what firmware
versions exist for Eilik vs. QEILIK vs. PANXER vs. MATICONTROLLER.

## Devices supported (from `DevEnum.py`)

```python
class DevType(Enum):
    EILIK = ...
    PANXER = ...
    MATICONTROLLER = ...
    QEILIK = ...
```

So EnergizeLab also drives PANXER (the larger Eilik?) and
MatiController (likely the Matic / smart home product).

## PYZ-encrypted PYZ files — what we have

The app code is encrypted in the PYZ archive. pyinstxtractor-ng
preserved the strings + bytecode (with the standard `0x0D 6F 0A`
magic) and we recovered:

* All ASCII/UTF-8 docstrings and constants.
* All bytecodes (loaded via xdis.load as Python 3.10 code objects).
* Full `format_data`, `sum_data`, `ping_data`, `inst_data`,
  `CheckDataBase`, `check_data` source reconstruction.

We did NOT need to break the AES layer — the constants and
docstrings already tell us the full protocol.

## What we should implement in our SDK next

1. **`read_display()`** — send cmd `0xA3`, decode 1024-byte payload.
2. **`write_display(payload_1024B)`** — send cmd `0xA4` with data.
3. **`read_servo_angles()`** — send cmd `0xA1`.
4. **`read_running_number()`** — send cmd `0xA5`.
5. A **packet wrapper** that uses the canonical `format_data()`
   from `PackAnalyData` so we know our checksums and lengths
   match what the official app produces.
6. A **stream framer** (`CheckDataBase.check_data`) so we can
   robustly read responses (we currently do a single read after
   each write; this is brittle for multi-packet replies).

## Audit gap

The reference SDK we based our motion code on uses an
**incomplete protocol** (just `cmd 0xA2` and a token). The
official app uses `format_data()` which adds a checksum,
exact length, and packet framing. Our motion code works
because the firmware is tolerant, but for the new commands
(`0xA3`/`0xA4`/`0xA5`) we should use the canonical
`format_data()` so we don't get garbage replies.

## Next file to investigate

`EilikPerameter.pyc` — likely has the magic sequence the
firmware needs to enter "parameter mode" before responding
to `cmd=0xA1`-`0xA6` reads/writes. Worth decompiling if
`0xA3` read returns nothing.