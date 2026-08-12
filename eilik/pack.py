"""
Canonical Eilik packet format from `PackAnalyData.format_data`
in the official `EnergizeLab.exe` (PyInstaller-bundled Python 3.10
app by Shenzhen Zhuneng Technology, the maker of Eilik).

Reconstructed from the decompiled `FirmwareBase/PackAnalyData.pyc`
in `reversing/_energizelab_extract/EnergizeLab.exe_extracted/`.
The docstrings survived AES encryption and the bytecode constants
fully reconstruct the functions.

Frame layout (USB short form, headId omitted, no BLE token):

    +0   "aa aa aa"          3 bytes  magic
    +3   length              2 bytes  little-endian u16, includes itself+cmd+data+checksum
    +5   instruction/data    N bytes  raw bytes (cmd, then any subcmd/data)
    +5+N checksum            1 byte   = (~sum(length_lo, length_hi, instruction..data)) & 0xFF

Per the bytecode (`PackAnalyData.format_data`), the length is packed as
`struct.pack('<H', len(data) + 3)`, giving 2 bytes little-endian:

* `format_data([0x01])`        → `aa aa aa 04 00 01 fa`
* `format_data([0x03, 0x05])`  → `aa aa aa 05 00 03 05 f6`
* `format_data([])`            → `aa aa aa 03 00 fb`  (no body, just magic+length+chk)

The `+3` in `len(data) + 3` covers the 2 length bytes + 1 checksum byte.

The official Chinese docstring says "length=length+instruction+len(data)+check"
which counts to 4 for non-empty data; the code's `len(data) + 3` counts
the 2-byte length as a single field. Both interpretations describe the
same on-wire frame.

Checksum is `sum_data(out[3:])` = `(~sum(length_lo, length_hi, ...)) & 0xFF`.
"""
from __future__ import annotations
import struct
from typing import Iterable, List, Optional


MAGIC = bytes([0xAA, 0xAA, 0xAA])


def checksum(buf: Iterable[int]) -> int:
    """1-byte checksum: (~sum(bytes)) & 0xFF."""
    s = 0
    for b in buf:
        s = (s + b) & 0xFF
    return (~s) & 0xFF


def format_data(data: Iterable[int]) -> bytes:
    """
    Build a complete Eilik USB frame:
    `aa aa aa <length:u16le> <data...> <checksum>`
    The data passed in starts with the instruction byte (e.g. `[0x01]` for ping).
    """
    data_list = list(data)
    length = len(data_list) + 3  # +3 = length_field(2 bytes treated as one) + checksum_byte
    out = bytearray()
    out.extend(MAGIC)
    out.extend(struct.pack('<H', length))
    out.extend(data_list)
    out.append(checksum(out[3:]))  # checksum over length..data
    return bytes(out)


def ping_data() -> bytes:
    """Cmd 0x01 — ping / request MCU info."""
    return format_data([0x01])


def inst_data(inst1: int, inst2: Optional[int] = None,
              data: Optional[Iterable[int]] = None) -> bytes:
    """
    Build `[inst1, opt(inst2), opt(data)]` and wrap with header+checksum.
    Matches `PackAnalyData.inst_data` exactly.
    """
    out: List[int] = []
    if inst1 is not None:
        out.append(inst1 & 0xFF)
    if inst2 is not None:
        out.append(inst2 & 0xFF)
    if data is not None:
        out.extend(int(b) & 0xFF for b in data)
    return format_data(out)


def write_servo(servos: Iterable[tuple]) -> bytes:
    """
    Cmd 0xA2 — write servo angles.
    `servos` is an iterable of (servo_id, position_16bit).
    Per the official docstring, the body is:
        count, (id, pos_l, pos_h) x count
    The firmware accepts up to 4 servos per packet.
    """
    servo_list = list(servos)
    payload = [len(servo_list) & 0xFF]
    for sid, pos in servo_list:
        payload.append(int(sid) & 0xFF)
        payload.append(int(pos) & 0xFF)
        payload.append((int(pos) >> 8) & 0xFF)
    return inst_data(0xA2, None, payload)


def read_display() -> bytes:
    """Cmd 0xA3 — read current display content (firmware returns 1024-byte payload)."""
    return inst_data(0xA3, None, None)


def write_display(payload_1024b: Iterable[int]) -> bytes:
    """Cmd 0xA4 — write display content. Payload is 1024 bytes raw framebuffer."""
    return inst_data(0xA4, None, payload_1024b)


def read_servo_angles() -> bytes:
    """Cmd 0xA1 — read current servo angles from the firmware."""
    return inst_data(0xA1, None, None)


def read_running_number() -> bytes:
    """Cmd 0xA5 — read the currently-playing animation/sound index."""
    return inst_data(0xA5, None, None)


def write_running_number(index: int) -> bytes:
    """Cmd 0xA6 — write the currently-playing animation/sound index."""
    return inst_data(0xA6, None, [int(index) & 0xFF])


class FrameBuffer:
    """
    Stream framer for incoming bytes. Mirrors the official app's
    `CheckDataBase.check_data()` but FIXES the upstream bug where the
    official code reads length as `struct.unpack('<H', check_data[-2:None])`
    (last TWO bytes, which are the body) instead of the next TWO bytes
    after the magic. In practice the firmware never sends back-to-back
    frames so this bug is harmless; we still fix it for robustness.

    Detects `aa aa aa <length> <body>` frames even when they arrive in
    chunks across multiple `feed()` calls.
    """

    MAGIC_BYTES = b"\xaa\xaa\xaa"
    RESET_GAP_MS = 20  # matched from `timedelta(milliseconds=20)`

    def __init__(self):
        self.buf = bytearray()
        self.frame_length = 0
        self.last_byte_at = 0.0

    def feed(self, chunk: bytes) -> List[bytes]:
        """Feed bytes; returns a list of complete frames (raw bytes)."""
        import time
        now = time.monotonic()
        if now - self.last_byte_at > 0.020:
            self.buf.clear()
            self.frame_length = 0
        self.last_byte_at = now
        self.buf.extend(chunk)
        return self._extract()

    def _extract(self) -> List[bytes]:
        out: List[bytes] = []
        while True:
            if len(self.buf) < 3:
                return out
            if self.buf[:3] != self.MAGIC_BYTES:
                self.buf.pop(0)
                continue
            if len(self.buf) < 5:
                return out
            if self.frame_length == 0:
                # length is 2 bytes little-endian at offset 3..5
                self.frame_length = self.buf[3] | (self.buf[4] << 8)
                if self.frame_length < 3:
                    self.buf.clear()
                    self.frame_length = 0
                    continue
            total = self.frame_length + 3  # total bytes incl magic
            if len(self.buf) < total:
                return out
            frame = bytes(self.buf[:total])
            self.buf = self.buf[total:]
            self.frame_length = 0
            out.append(frame)
        return out