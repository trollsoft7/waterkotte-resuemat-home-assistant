"""Tests for the Resümat serial protocol."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import struct
import sys
import unittest

PROTOCOL_PATH = (
    Path(__file__).parents[1]
    / "custom_components"
    / "waterkotte_resuemat"
    / "protocol.py"
)
SPEC = importlib.util.spec_from_file_location("resumat_protocol", PROTOCOL_PATH)
assert SPEC is not None and SPEC.loader is not None
PROTOCOL = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PROTOCOL
SPEC.loader.exec_module(PROTOCOL)

FrameDecoder = PROTOCOL.FrameDecoder
READ_RANGES = PROTOCOL.READ_RANGES
ResumatProtocolError = PROTOCOL.ResumatProtocolError
ResumatClient = PROTOCOL.ResumatClient
build_read_command = PROTOCOL.build_read_command
crc16 = PROTOCOL.crc16
decode_readings = PROTOCOL.decode_readings


class ProtocolTests(unittest.TestCase):
    """Verify frame generation and value decoding."""

    def test_read_commands_match_flow_checksums(self) -> None:
        """Read requests retain the command bytes used in the flow."""
        self.assertEqual(
            build_read_command(0x0000, 0x00F3),
            bytes.fromhex("10020115000000f310037c32"),
        )
        self.assertEqual(
            build_read_command(0x00F3, 0x0046),
            bytes.fromhex("1002011500f300461003f373"),
        )

    def test_integration_exposes_no_write_operations(self) -> None:
        """The protocol client only builds and sends read requests."""
        client = ResumatClient("/dev/null")
        self.assertFalse(hasattr(client, "async_write_float"))
        self.assertFalse(hasattr(client, "async_write_enabled"))
        self.assertEqual(build_read_command(0, 4)[2:4], b"\x01\x15")

    def test_client_reports_communication_status_changes(self) -> None:
        """Every communication phase is exposed to registered listeners."""
        client = ResumatClient("/dev/null")
        changes: list[str] = []
        client.set_status_callback(lambda: changes.append(client.status))
        for status in (
            "connecting",
            "waking",
            "sending_request",
            "waiting_response",
            "receiving",
            "parsing",
            "idle",
        ):
            client.set_status(status)

        self.assertEqual(changes, [
            "connecting",
            "waking",
            "sending_request",
            "waiting_response",
            "receiving",
            "parsing",
            "idle",
        ])

    def test_decoder_handles_split_escaped_frames(self) -> None:
        """The stream decoder waits for split frames and unescapes DLE bytes."""
        response = make_response(0x0017, b"first\x10second")
        decoder = FrameDecoder()
        self.assertEqual(decoder.feed(response[:7]), [])
        self.assertEqual(
            decoder.feed(response[7:]),
            [PROTOCOL.Frame(0x0017, b"first\x10second")],
        )

    def test_decoder_validates_crc(self) -> None:
        """A complete response with an invalid checksum is rejected."""
        response = bytearray(make_response(0x0017, b"data"))
        response[-3] ^= 0x01
        with self.assertRaises(ResumatProtocolError):
            FrameDecoder().feed(response)

    def test_decode_readings_uses_controller_addresses(self) -> None:
        """Read-only measurements map to controller addresses."""
        data = bytearray(sum(length for _, length in READ_RANGES))
        for address, value in {
            0x0008: 4.5,
            0x0014: 30.0,
            0x0024: 48.25,
            0x006A: 1234.0,
            0x00F4: 20.0,
            0x00F8: 28.0,
            0x013B: 52.0,
        }.items():
            struct.pack_into("<f", data, address, value)
        data[0x00F3] = 1
        data[0x0134] = 1
        data[0x00DF] = 1
        data[0x00E1] = 0

        readings = decode_readings(data)

        self.assertEqual(readings["outdoor_temperature"], 4.5)
        self.assertEqual(readings["return_temperature_target"], 30.0)
        self.assertEqual(readings["hot_water_temperature"], 48.25)
        self.assertEqual(readings["compressor_operating_hours"], 1234.0)
        self.assertEqual(readings["heating_setpoint"], 28.0)
        self.assertEqual(readings["hot_water_setpoint"], 52.0)
        self.assertTrue(readings["heating_disabled"])
        self.assertTrue(readings["hot_water_disabled"])
        self.assertTrue(readings["heating_running"])
        self.assertFalse(readings["hot_water_running"])


def make_response(message_type: int, payload: bytes) -> bytes:
    """Build a controller response frame for decoder tests."""
    body = message_type.to_bytes(2, "big") + payload
    escaped = body.replace(b"\x10", b"\x10\x10")
    return (
        b"\x16\x10\x02"
        + escaped
        + b"\x10\x03"
        + crc16(body).to_bytes(2, "big")
        + b"\x16"
    )


if __name__ == "__main__":
    unittest.main()
