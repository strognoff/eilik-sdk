#!/usr/bin/env python3
"""Extract likely payload bytes from a USBPcap/Wireshark capture.

Requires tshark on PATH. This intentionally prints conservative text output so
captures can be inspected without adding binary parsing dependencies.
"""

from __future__ import annotations

import argparse
import re
import shutil
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract USB payload hex from a capture.")
    parser.add_argument("capture", type=Path)
    parser.add_argument("--contains", default="aa aa aa", help="Only show payloads containing this hex pattern.")
    parser.add_argument("--all", action="store_true", help="Show every packet with payload bytes.")
    args = parser.parse_args()

    wanted = normalize_hex(args.contains)
    stdout = run_tshark(args.capture)

    count = 0
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

    if count == 0:
        print("No matching payloads found.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
