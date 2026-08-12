# formatData_v2 commands extracted from official Eilik Android app

Decompiled from the official EnergizeLab APK (`app-release.apk`,
EnergizeLab React Native app, Hermes bytecode decompiled via `hermes-decompiler`).

## Frame structure (BLE / long format)

```text
+0  "aa aa aa"         3 bytes  magic
+3  length             1 byte   total bytes after magic, INCLUDING the length byte
+4  headId (a0)        1 byte
+5  token (placeholder) 5 bytes  zeros in our captures; real BLE session uses 5-byte counter/nonce
+10 cmd (a1)           1 byte
+11 pktNum             2 bytes BE
+13 totPkts            2 bytes BE
+15 data (a2)          N bytes
+15+N checksum         1 byte   generalCheckSum over bytes +3 .. +15+N-1
```

Constants from `BLEARGSLENS`:

```js
HEADERLEN:3, LENTHLEN:1, INSTRUCTIONLEN:1,
ENCRYPTIONLEN:5, CHECKLEN:1,
MAXPACKDATALEN:112, PACKNUMINFOLEN:2
```

A frame with empty data and a single packet is therefore 16 bytes on the
wire (3 + 1 + 1 + 5 + 1 + 2 + 2 + 0 + 1).

The short frames we saw in the USB capture
(`aa aa aa 04 00 01 fa`, `aa aa aa 04 00 20 db`,
`aa aa aa 09 00 02 00 09 00 00 00 eb`) follow the SAME structure but
with an implicit zero-length token field when `headId` is `00` and
the writer path omits the encryption field. The math still works
when length is computed as `1 + 1 + cmdLen + tokenLen + dataLen + 1`
and `tokenLen` is omitted for `headId=0x00` writes.

## Commands actually sent by the official app

HeadId / cmd / data / inferred purpose.

| headId | cmd | data            | call site(s)              | purpose |
|--------|-----|-----------------|---------------------------|---------|
| 00     | 00  | ''              | startCheckBodyInfo        | idle / heartbeat |
| 01     | 08  | (json)          | startCheckBodyInfo        | initial body-info handshake |
| 01     | 81  | ''              | getParams (read)          | read parameter block |
| 01     | 01  | (json)          | getParams                 | parameter read result |
| 02     | 83  | (json)          | slidingComplete           | UX / gesture event ack |
| 02     | 92  | (json)          | getParams response        | parameter write ack |
| 02     | 03  | (json)          | submitDeviceName          | submit name |
| 03     | 01  | ''              | bulk data                 | resource sync / fetch |
| 03     | 07  | ''              | bulk data                 | resource sync start |
| 04     | 08  | (binary)        | OTA                       | firmware/resource update packet |
| 04     | 91  | (binary)        | OTA start                 | firmware/resource update begin |
| 08     | 08  | (json)          | getParams                 | parameter read alt |
| 08     | 87  | (json)          | getParams (write)         | parameter write |

Notes:
* `headId=0x02` is the application data namespace (the app talks to
  Eilik about its own config and gestures).
* `headId=0x03` is the resource namespace (read/write of resource
  packs, including the update-looking payload we saw in the USB
  capture).
* `headId=0x04` is the OTA namespace (firmware + resource bundle
  uploads).
* `headId=0x08` is used as a parameter read/write group with a
  different sub-protocol.
* No `headId / cmd` combination in the official app corresponds to
  an obvious "show this face" or "play this sound" command. The
  app's only "face" assets (`face_modal`, `face_avatar_1..5`,
  `face_avatar_camera`) are profile pictures stored on the phone,
  not commands sent to the robot.

## How to use this from the SDK

1. Build a single long-format packet via the same layout
   (`formatData_v2` in `_reports/hermes.decompiled.js` is the
   reference, line ~289463).
2. For multi-packet payloads, set `pktNum` from 1..totPkts and
   slice `data` into `MAXPACKDATALEN = 112` byte chunks.
3. Append `generalCheckSum` over `length .. data`.

The BLE write path uses `safeWriteCharacteristicForDevice` with
`{ response: true, type: 'hex' }`; the USB equivalent is a single
`write` on `/dev/ttyACM0`. The long-format packets already work
through the existing SDK entry point if we route them via BLE on
Android or via a USB-BLE bridge on WSL.
