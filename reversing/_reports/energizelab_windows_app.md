# EnergizeLab Windows App Notes

Date: 2026-08-12

## Bundle

`reversing/EnergizeApp/EnergizeLab.exe` is a PyInstaller Windows GUI app using Python 3.10. It ships as an MSIX-style folder with `python310.dll`, PySide6, PIL, pyserial, requests, cryptography, and `tinyaes`.

The MSIX manifest requests:

- `usb`
- `serialcommunication`

The PyInstaller archive extracts to `reversing/EnergizeLab.exe_extracted/`. The useful application modules live under:

`PYZ-00.pyz_extracted/FirmwareBase/`

## FirmwareBase Modules

Important modules recovered from the embedded bytecode:

- `Config.pyc`
- `SearchDevice.pyc`
- `PackAnalyData.pyc`
- `FirmwareUpdate.pyc`
- `FirmwareWriteFlash.pyc`
- `UpdateV2.pyc`
- `UploadRobotInfo.pyc`
- `EilikPerameter.pyc`
- `ServoInsGe.pyc`
- `DevEnum.pyc`
- `Info.pyc`

The standard source decompilers available here do not support Python 3.10 bytecode, but `xdis`/`pydisasm` can read the module constants and opcode flow.

## Serial Mode

The Windows updater searches serial ports and opens the device at:

```text
baudrate: 1000000
timeout: 5
write_timeout: 8
```

This is different from the legacy servo SDK baud path we inherited from the public controller code.

## Frame Format

`FirmwareBase/PackAnalyData.pyc` implements the short USB frame format:

```text
aa aa aa
length_le16
payload
checksum
```

`length = len(payload) + 3`

That length includes the 2 length bytes, payload bytes, and checksum byte, but not the 3-byte `aa aa aa` header.

Checksum:

```python
(~sum(length_bytes + payload)) & 0xff
```

This matches the captured short frames, for example:

```text
aa aa aa 04 00 01 fa
```

## Embedded Protocol Notes

`PackAnalyData.pyc` contains a Chinese protocol comment documenting command IDs:

| Command | Meaning |
| --- | --- |
| `0x01` | ping / device info |
| `0x02` | confirm update version |
| `0x03` | content/resource update |
| `0x04` | firmware write to flash after resources |
| `0x05` | direct flash write |
| `0x20` | read all parameters, returns 2 KB |
| `0x21` | read one parameter |
| `0x31` | write parameter |
| `0x41` | retry/init SD card |
| `0x42` | format SD card |
| `0xA1` | read servo angle |
| `0xA2` | write servo angle |
| `0xA3` | read current display content |
| `0xA4` | write current display content, 1024 bytes |
| `0xA5` | read current running number |
| `0xA6` | write current running number |

This is the first concrete clue that the Eilik face display may be commandable over USB.

## Display / Screen

The app does not appear to expose a UI action for arbitrary display writes, and no module call site was found actively using `0xA3` or `0xA4`.

However, the protocol comment explicitly documents:

- `0xA3`: read current display content
- `0xA4`: write current display content with a 1024-byte payload

Likely next test path:

1. Open Eilik in the updater serial mode at `1000000` baud.
2. Send `0xA3` using the short frame builder.
3. Read and inspect the returned current display buffer.
4. Only after confirming size/shape, try a reversible `0xA4` write using the previously read buffer or a minimal safe test pattern.

Do not blindly send arbitrary `0xA4` content until `0xA3` confirms the expected buffer shape.

## Audio / Microphone

No direct microphone audio streaming command was found in the Windows updater modules.

Relevant telemetry/settings fields found:

- `screen_light`
- `volume`
- `eilik_volume_ctr`
- `eilik_talk_style`
- `set_brightness_volume_times`
- `record_*` counters
- `beat_*` counters

This suggests the updater can read stored telemetry/settings related to screen brightness, volume, records, and beat/noise features, but it does not expose raw microphone audio or a play-sound command.

## Resource Update Flow

The updater downloads or reads:

- `firmware_info_compress.json`
- `firmware_info.xlsx`
- `update.bin`
- resource files under `resource`

Important URLs/constants:

```text
https://file.energizelab.com.cn/
http://175.24.102.176/software/energizelab/robot/user/
http://45.32.81.33:789/software/energizelab/robot/user/
```

The resource update flow uses command `0x03` subcommands:

- `0x01`: file compare by name/time
- `0x02`: write content
- `0x03`: complete config / overall checksum

Block sizes:

- normal resource chunks: `5120`
- QEL/Eiliko-style path uses `61440` in places

## Device Types

`DevEnum.pyc` defines:

- `EL` = Eilik
- `QEL` = Q/Eiliko-style Eilik
- `PX` = Panxer
- `MC` = Maticontroller

The updater has separate paths for `EL`, `QEL`, `PX`, and `MC`.

## Practical Conclusions

1. The Windows app gives us a stronger USB protocol map than the Android APK.
2. The display has a documented `0xA3/0xA4` read/write path.
3. Arbitrary text is still not solved. We first need to learn the 1024-byte display buffer format.
4. The safest next experiment is a read-only `0xA3` probe, not a write.
5. Microphone/raw audio is still not exposed by this updater code.
