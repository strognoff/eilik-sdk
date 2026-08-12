from eilik.protocol import (
    HB1,
    build_servo_frame,
    build_servo_payload,
    calculate_checksum,
    extract_session_token,
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
