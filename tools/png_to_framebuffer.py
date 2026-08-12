#!/usr/bin/env python3
"""Convert a 128x64 PNG (or any size — auto-resized) into Eilik's 1024-byte framebuffer.

Usage:
    python tools/png_to_framebuffer.py <input.png> <output.bin>

The output is a raw 1024-byte file that can be fed to:
    python -m eilik write_display --image <output.bin>

Encoding: SSD1306 page-mode, 8 pages × 128 columns × LSB-first within each byte.
"""

from __future__ import annotations

import argparse
import sys
import zlib
import struct
from pathlib import Path


def decode_png(path: Path) -> tuple[int, int, list[int]]:
    """Tiny PNG decoder (8-bit grayscale or RGB, no filtering beyond None/Sub/Up/Average/Paeth)."""
    data = path.read_bytes()
    assert data[:8] == b'\x89PNG\r\n\x1a\n', "not a PNG"
    pos = 8
    width = height = 0
    color = 0
    bit_depth = 0
    idat = b''
    while pos < len(data):
        length = struct.unpack('>I', data[pos:pos+4])[0]
        tag = data[pos+4:pos+8]
        chunk = data[pos+8:pos+8+length]
        pos += 8 + length + 4  # skip CRC
        if tag == b'IHDR':
            width, height, bit_depth, color = struct.unpack('>IIBB', chunk[:10])
        elif tag == b'IDAT':
            idat += chunk
        elif tag == b'IEND':
            break
    raw = zlib.decompress(idat)
    # Channel count
    chans = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color]
    bpp = chans * (bit_depth // 8)
    stride = width * bpp
    pixels = bytearray()
    prev_row = bytearray(stride)
    for y in range(height):
        filt = raw[y * (stride + 1)]
        row = bytearray(raw[y * (stride + 1) + 1: y * (stride + 1) + 1 + stride])
        if filt == 0:
            pass
        elif filt == 1:  # Sub
            for x in range(bpp, stride):
                row[x] = (row[x] + row[x - bpp]) & 0xFF
        elif filt == 2:  # Up
            for x in range(stride):
                row[x] = (row[x] + prev_row[x]) & 0xFF
        elif filt == 3:  # Average
            for x in range(stride):
                left = row[x - bpp] if x >= bpp else 0
                row[x] = (row[x] + (left + prev_row[x]) // 2) & 0xFF
        elif filt == 4:  # Paeth
            for x in range(stride):
                a = row[x - bpp] if x >= bpp else 0
                b = prev_row[x]
                c = prev_row[x - bpp] if x >= bpp else 0
                p = a + b - c
                pa = abs(p - a); pb = abs(p - b); pc = abs(p - c)
                if pa <= pb and pa <= pc: pred = a
                elif pb <= pc: pred = b
                else: pred = c
                row[x] = (row[x] + pred) & 0xFF
        else:
            raise ValueError(f"unsupported PNG filter {filt}")
        pixels.extend(row)
        prev_row = row
    return width, height, pixels


def to_grayscale(pixels: list[int], width: int, height: int, chans: int) -> list[int]:
    """Reduce to 8-bit grayscale luminance."""
    out = []
    for y in range(height):
        for x in range(width):
            i = (y * width + x) * chans
            if chans == 1:
                out.append(pixels[i])
            elif chans == 3 or chans == 4:
                r, g, b = pixels[i], pixels[i + 1], pixels[i + 2]
                out.append(int(0.299 * r + 0.587 * g + 0.114 * b))
            elif chans == 2:
                v = pixels[i]
                a = pixels[i + 1]
                out.append(int(v * (a / 255)))
    return out


def resize_nearest(gray: list[int], src_w: int, src_h: int, dst_w: int, dst_h: int) -> list[int]:
    out = []
    for y in range(dst_h):
        sy = int(y * src_h / dst_h)
        for x in range(dst_w):
            sx = int(x * src_w / dst_w)
            out.append(gray[sy * src_w + sx])
    return out


def to_framebuffer(gray: list[int], width: int = 128, height: int = 64, threshold: int = 128) -> bytes:
    """Convert grayscale pixels to Eilik's 1024-byte page-mode framebuffer."""
    assert len(gray) == width * height
    # 8 pages, each 128 columns × 8 rows
    fb = bytearray(1024)
    for page in range(8):
        for col in range(128):
            byte = 0
            for row in range(8):
                y = page * 8 + row
                x = col
                pixel = gray[y * width + x]
                if pixel < threshold:
                    byte |= (1 << row)  # LSB-first
            fb[page * 128 + col] = byte
    return bytes(fb)


# Bit-reverse table for 8-bit values (used by rotate_180 below).
_BIT_REVERSE_TABLE = bytes(int(f"{b:08b}"[::-1], 2) for b in range(256))


def rotate_180(buf: bytes | bytearray) -> bytes:
    """Rotate a 1024-byte SSD1306 framebuffer by 180°.

    Eilik's OLED panel (or firmware) renders the framebuffer rotated 180° from
    what the SDK reads back. So when you build a framebuffer from a PNG and
    send it, the user's image appears upside-down on the physical display.

    To get the image to appear right-side-up, rotate the framebuffer by 180°
    BEFORE sending.

    Rotation: page[p] ↔ page[7-p] AND column[c] ↔ column[127-c] AND bit[b] ↔ bit[7-b].
    """
    assert len(buf) == 1024, f"framebuffer must be 1024 bytes (got {len(buf)})"
    out = bytearray(1024)
    for p in range(8):
        src_page = 7 - p
        for c in range(128):
            src_col = 127 - c
            out[p * 128 + c] = _BIT_REVERSE_TABLE[buf[src_page * 128 + src_col]]
    return bytes(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert PNG to Eilik 1024-byte framebuffer.")
    parser.add_argument("input", type=Path, help="Input PNG (any size; auto-resized to 128x64).")
    parser.add_argument("output", type=Path, help="Output 1024-byte raw framebuffer.")
    parser.add_argument("--threshold", type=int, default=128,
                        help="Grayscale threshold for 1bpp conversion (default: 128).")
    parser.add_argument("--invert", action="store_true",
                        help="Invert (use if your PNG is white-on-black, Eilik is black-on-white).")
    args = parser.parse_args(argv)

    width, height, pixels = decode_png(args.input)
    chans = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[0]  # default
    # detect channel count from data size
    expected = width * height
    actual = len(pixels)
    if actual == expected:
        chans = 1
    elif actual == expected * 3:
        chans = 3
    elif actual == expected * 4:
        chans = 4
    elif actual == expected * 2:
        chans = 2
    else:
        print(f"unexpected pixel size: {actual} bytes for {width}x{height}", file=sys.stderr)
        return 1

    gray = to_grayscale(pixels, width, height, chans)
    if args.invert:
        gray = [255 - g for g in gray]
    gray = resize_nearest(gray, width, height, 128, 64)
    fb = to_framebuffer(gray, threshold=args.threshold)
    args.output.write_bytes(fb)
    print(f"Wrote {len(fb)} bytes to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())