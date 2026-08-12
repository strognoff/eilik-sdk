from eilik.protocol import (
    HB1,
    OFFICIAL_SESSION_ACK,
    OFFICIAL_SESSION_START,
    OFFICIAL_STATUS_REQUEST,
    build_command_frame,
    build_servo_frame,
    build_servo_payload,
    calculate_checksum,
    extract_session_token,
    has_command_reply,
    iter_frames,
)


def test_checksum_generation_matches_reference_formula():
    payload = bytes.fromhex("14 00 61 11 22 33 44 55 03 01 04 01 dc 05 00 00 00 00 00")

    assert calculate_checksum(payload) == 255 - (sum(payload) % 256)


def test_packet_generation_matches_original_shape():
    token = bytes.fromhex("11 22 33 44 55")
    frame = build_servo_frame(token, motor_id=4, position=1500)
    payload = build_servo_payload(token, motor_id=4, position=1500)

    assert frame.hex(" ") == (
        "aa aa aa 14 00 61 11 22 33 44 55 03 01 04 01 dc 05 00 00 00 00 00 "
        f"{calculate_checksum(payload):02x}"
    )


def test_session_token_parsing_from_handshake_reply():
    reply = bytes.fromhex("aa aa aa 0a 00 61 de ad be ef 01 99 88")

    assert extract_session_token(reply) == bytes.fromhex("de ad be ef 01")


def test_session_token_parsing_tolerates_leading_noise():
    reply = b"\x00\x01" + bytes.fromhex("aa aa aa 0a 00 61 ca fe ba be 02 99")

    assert extract_session_token(reply) == bytes.fromhex("ca fe ba be 02")


def test_hb1_is_reference_heartbeat():
    assert HB1.hex(" ") == "aa aa aa 0a 00 61 e4 c6 f1 ca 83 ff ad"


def test_captured_official_status_frame_matches_capture():
    assert build_command_frame(0x01) == OFFICIAL_STATUS_REQUEST
    assert OFFICIAL_STATUS_REQUEST.hex(" ") == "aa aa aa 04 00 01 fa"


def test_captured_official_session_start_matches_capture():
    assert build_command_frame(0x02, bytes.fromhex("00 09 00 00 00")) == OFFICIAL_SESSION_START
    assert build_command_frame(0x02) == OFFICIAL_SESSION_ACK


def test_iter_frames_finds_checked_frames_with_noise():
    buffer = b"\x00\xff" + OFFICIAL_STATUS_REQUEST + b"junk" + OFFICIAL_SESSION_ACK

    assert iter_frames(buffer) == [OFFICIAL_STATUS_REQUEST, OFFICIAL_SESSION_ACK]
    assert has_command_reply(buffer, 0x01)
    assert has_command_reply(buffer, 0x02)
    assert not has_command_reply(buffer, 0x03)
