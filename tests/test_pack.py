"""Unit tests for the canonical Eilik packet builder from PackAnalyData."""

from eilik.pack import (
    MAGIC,
    FrameBuffer,
    checksum,
    format_data,
    inst_data,
    ping_data,
    read_display,
    read_running_number,
    read_servo_angles,
    write_display,
    write_running_number,
    write_servo,
)


def _hex(b):
    """Format bytes like `aa aa aa 04 00 01 fa` for readable asserts."""
    return " ".join(f"{x:02x}" for x in b)


def test_checksum_matches_official():
    # length bytes + cmd: ~sum([0x04, 0x00, 0x01]) & 0xFF = 0xFA
    assert checksum([0x04, 0x00, 0x01]) == 0xFA


def test_ping_matches_captured_status_request():
    """`aa aa aa 04 00 01 fa` is the captured official-app ping."""
    frame = ping_data()
    assert _hex(frame) == "aa aa aa 04 00 01 fa"
    assert frame.startswith(MAGIC)


def test_inst_data_no_subcmd_or_data():
    """`cmd=0xA1, subcmd=None, data=None` should produce a 1-cmd-body frame."""
    frame = inst_data(0xA1, None, None)
    assert _hex(frame) == "aa aa aa 04 00 a1 5a"


def test_write_servo_single():
    # cmd=0xA2, count=1, id=1, pos=1500 -> 5-byte body
    frame = write_servo([(1, 1500)])
    assert _hex(frame) == "aa aa aa 08 00 a2 01 01 dc 05 72"


def test_read_display_payload():
    frame = read_display()
    assert _hex(frame) == "aa aa aa 04 00 a3 58"


def test_read_servo_angles_payload():
    frame = read_servo_angles()
    assert _hex(frame) == "aa aa aa 04 00 a1 5a"


def test_read_running_number_payload():
    frame = read_running_number()
    assert _hex(frame) == "aa aa aa 04 00 a5 56"


def test_write_running_number_index():
    frame = write_running_number(7)
    assert _hex(frame) == "aa aa aa 05 00 a6 07 4d"


def test_write_display_1024_byte_payload():
    payload = bytes(range(256)) * 4  # exactly 1024 bytes
    frame = write_display(payload)
    assert frame.startswith(MAGIC)
    assert frame[5] == 0xA4
    # magic(3) + length(2) + cmd(1) + data(1024) + checksum(1) = 1031
    assert len(frame) == 1031


def test_frame_buffer_parses_single_frame():
    fb = FrameBuffer()
    frames = fb.feed(b"\xaa\xaa\xaa\x04\x00\xa3\x58")
    assert len(frames) == 1
    assert _hex(frames[0]) == "aa aa aa 04 00 a3 58"


def test_frame_buffer_parses_split_chunk():
    fb = FrameBuffer()
    out1 = fb.feed(b"\xaa\xaa\xaa\x04")
    out2 = fb.feed(b"\x00\x01\xfa")
    assert out1 == []
    assert len(out2) == 1
    assert _hex(out2[0]) == "aa aa aa 04 00 01 fa"


def test_frame_buffer_rejects_bogus_length():
    """Length field is u16; values < 3 are bogus."""
    fb = FrameBuffer()
    frames = fb.feed(b"\xaa\xaa\xaa\x01\x00\xff")
    assert frames == []
    assert fb.frame_length == 0
    assert bytes(fb.buf) == b""


def test_frame_buffer_extracts_multiple_frames():
    fb = FrameBuffer()
    blob = b"\xaa\xaa\xaa\x04\x00\x01\xfa" * 2
    frames = fb.feed(blob)
    assert len(frames) == 2
    assert _hex(frames[0]) == "aa aa aa 04 00 01 fa"
    assert _hex(frames[1]) == "aa aa aa 04 00 01 fa"