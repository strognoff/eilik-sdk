#!/usr/bin/env python3
"""Extract likely payload bytes from a USBPcap/Wireshark capture.

Uses tshark when available and falls back to a small built-in USBPcap/pcapng
parser for Windows captures.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path


FIELDS = [
    "frame.number",
    "frame.time_relative",
    "usb.endpoint_address",
    "usb.src",
    "usb.dst",
    "usb.capdata",
    "usb.data_fragment",
    "data.data",
]


def normalize_hex(value: str) -> str:
    pairs = re.findall(r"[0-9a-fA-F]{2}", value)
    return " ".join(pair.lower() for pair in pairs)


def direction(endpoint: str) -> str:
    try:
        ep = int(endpoint, 0)
    except ValueError:
        return "?"
    return "IN" if ep & 0x80 else "OUT"


def run_tshark(capture: Path) -> str:
    if not shutil.which("tshark"):
        raise SystemExit("tshark is not installed or not on PATH. Install Wireshark/tshark first.")

    cmd = ["tshark", "-r", str(capture), "-T", "fields", "-E", "separator=\t"]
    for field in FIELDS:
        cmd.extend(["-e", field])

    result = subprocess.run(cmd, check=False, text=True, capture_output=True)
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or f"tshark failed with exit code {result.returncode}")
    return result.stdout


def iter_usbpcap_payloads(capture: Path):
    data = capture.read_bytes()
    pos = 0
    endian = "<"
    frame_number = 0

    while pos + 12 <= len(data):
        block_type, block_len = struct.unpack_from(endian + "II", data, pos)
        if block_type == 0x0A0D0D0A:
            byte_order_magic = struct.unpack_from("I", data, pos + 8)[0]
            endian = "<" if byte_order_magic == 0x1A2B3C4D else ">"
            block_type, block_len = struct.unpack_from(endian + "II", data, pos)
        if block_len < 12 or pos + block_len > len(data):
            break

        if block_type == 6:
            _interface_id, ts_high, ts_low, cap_len, _orig_len = struct.unpack_from(endian + "IIIII", data, pos + 8)
            packet = data[pos + 28 : pos + 28 + cap_len]
            if len(packet) >= 27:
                header_len = struct.unpack_from("<H", packet, 0)[0]
                if 27 <= header_len <= len(packet):
                    frame_number += 1
                    bus = struct.unpack_from("<H", packet, 17)[0]
                    device = struct.unpack_from("<H", packet, 19)[0]
                    endpoint = packet[21]
                    payload = packet[header_len:]
                    if payload:
                        timestamp = ((ts_high << 32) + ts_low) / 1_000_000
                        yield frame_number, timestamp, endpoint, bus, device, payload

        pos += block_len


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract USB payload hex from a capture.")
    parser.add_argument("capture", type=Path)
    parser.add_argument("--contains", default="aa aa aa", help="Only show payloads containing this hex pattern.")
    parser.add_argument("--all", action="store_true", help="Show every packet with payload bytes.")
    args = parser.parse_args()

    wanted = normalize_hex(args.contains)
    count = 0
    if shutil.which("tshark"):
        stdout = run_tshark(args.capture)
        for line in stdout.splitlines():
            cols = line.split("\t")
            cols += [""] * (len(FIELDS) - len(cols))
            frame, rel_time, endpoint, src, dst, *data_fields = cols
            payloads = [normalize_hex(value) for value in data_fields if normalize_hex(value)]
            if not payloads:
                continue
            payload = max(payloads, key=len)
            if not args.all and wanted not in payload:
                continue
            count += 1
            print(f"{frame}\t{rel_time}\t{direction(endpoint)}\tep={endpoint}\t{src}->{dst}\t{payload}")
    else:
        for frame, rel_time, endpoint, bus, device, payload_bytes in iter_usbpcap_payloads(args.capture):
            payload = payload_bytes.hex(" ")
            if not args.all and wanted not in payload:
                continue
            count += 1
            print(f"{frame}\t{rel_time:.6f}\t{direction(hex(endpoint))}\tep=0x{endpoint:02x}\tbus={bus},dev={device}\t{payload}")

    if count == 0:
        print("No matching payloads found.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        raise SystemExit(0)
