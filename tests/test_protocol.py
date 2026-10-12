"""Tests for the Resümat serial protocol."""

from __future__ import annotations

import asyncio
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
WAKEUP_COMMAND = PROTOCOL.WAKEUP_COMMAND
MIN_READ_REQUEST_INTERVAL = PROTOCOL.MIN_READ_REQUEST_INTERVAL
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

    def test_wakeup_matches_reference_driver(self) -> None:
        """Wake-up bytes match the captured Node-RED payload exactly."""
        expected = (
            b"AT "
            + bytes.fromhex(
                "10020115000000041003cb9b03"
                "10020115003000041003cb9de2889a"
                "100201150034000410037dc3aa"
            )
            + bytes(1024)
        )
        self.assertEqual(WAKEUP_COMMAND, expected)
        self.assertEqual(len(WAKEUP_COMMAND), 1068)

    def test_read_ranges_match_node_red_flow(self) -> None:
        """Only the two flow memory blocks are requested."""
        self.assertEqual(READ_RANGES, ((0x0000, 0x00F3), (0x00F3, 0x0046)))
        self.assertEqual(MIN_READ_REQUEST_INTERVAL, 30)

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
        """The decoder unescapes DLEs and waits for the requested packet size."""
        payload = b"first\x10second"
        response = make_response(PROTOCOL.READ_RESPONSE, payload)
        decoder = FrameDecoder()
        self.assertEqual(decoder.feed(response[:7], len(payload)), [])
        self.assertEqual(
            decoder.feed(response[7:], len(payload)),
            [PROTOCOL.Frame(PROTOCOL.READ_RESPONSE, payload)],
        )

    def test_response_start_matches_node_red_wire_frame(self) -> None:
        """A normal reply has the Node-RED 253-byte unescaped size."""
        payload_data = bytearray(range(243))
        payload_data[10] = 0x10
        payload_data[20] = 0x10
        payload_data[16] = 0x11
        payload = bytes(payload_data)
        response = make_response(PROTOCOL.READ_RESPONSE, payload)

        self.assertEqual(response[:3], b"\xff\x10\x02")
        self.assertEqual(len(response), 255)
        self.assertEqual(len(response.replace(b"\x10\x10", b"\x10")), 253)
        self.assertEqual(
            FrameDecoder().feed(response, len(payload)),
            [PROTOCOL.Frame(PROTOCOL.READ_RESPONSE, payload)],
        )

    def test_decoder_exposes_incomplete_frame_bytes(self) -> None:
        """Partial response data remains available for timeout diagnostics."""
        decoder = FrameDecoder()
        prefix = b"\xff\x10\x02\x00\x17"
        self.assertEqual(decoder.feed(prefix, 10), [])
        self.assertEqual(decoder.pending_data, prefix)

    def test_decoder_accepts_node_red_sized_second_block(self) -> None:
        """The second normal response is 80 bytes after DLE unescaping."""
        payload = bytes(range(0x46))
        response = make_response(PROTOCOL.READ_RESPONSE, payload)

        self.assertEqual(len(response.replace(b"\x10\x10", b"\x10")), 0x46 + 10)
        self.assertEqual(
            FrameDecoder().feed(response, 0x46),
            [PROTOCOL.Frame(PROTOCOL.READ_RESPONSE, payload)],
        )

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
            0x0020: 52.0,
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


class ReceiveTimeoutTests(unittest.TestCase):
    """Verify diagnostic details when the controller response is incomplete."""

    def test_timeout_includes_received_byte_count_and_frame(self) -> None:
        """A response timeout reports the bytes received so far."""
        asyncio.run(self._async_test_timeout_includes_received_byte_count())

    async def _async_test_timeout_includes_received_byte_count(self) -> None:
        class PartialReader:
            """Return a partial frame and then wait for more input."""

            def __init__(self) -> None:
                self.sent_partial_frame = False

            async def read(self, _size: int) -> bytes:
                if not self.sent_partial_frame:
                    self.sent_partial_frame = True
                    return b"\xff\x10\x02\x00\x17"
                await asyncio.Future()

        client = ResumatClient("/dev/null")
        client._reader = PartialReader()
        old_timeout = PROTOCOL.RESPONSE_TIMEOUT
        PROTOCOL.RESPONSE_TIMEOUT = 0.01
        try:
            with self.assertRaisesRegex(
                TimeoutError,
                "received 5 wire bytes; decoder buffer: ff10020017; "
                "received data: ff10020017",
            ):
                await client._async_receive(10)
        finally:
            PROTOCOL.RESPONSE_TIMEOUT = old_timeout

    def test_short_preamble_response_is_ignored(self) -> None:
        """Short frames do not satisfy a full block read response."""
        asyncio.run(self._async_test_short_preamble_response_is_ignored())

    async def _async_test_short_preamble_response_is_ignored(self) -> None:
        class PreambleReader:
            """Return a short response followed by a complete read response."""

            def __init__(self) -> None:
                self.chunks = [
                    make_response(0x0001, b"short"),
                    make_response(PROTOCOL.READ_RESPONSE, b"full-block"),
                ]

            async def read(self, _size: int) -> bytes:
                return self.chunks.pop(0)

        client = ResumatClient("/dev/null")
        client._reader = PreambleReader()
        self.assertEqual(await client._async_receive(10), b"full-block")

    def test_wakeup_is_sent_once_per_connection_without_acknowledgement(self) -> None:
        """Wake-up is a one-way unlock before directly starting the reads."""
        asyncio.run(self._async_test_wakeup_is_sent_once_per_connection())

    async def _async_test_wakeup_is_sent_once_per_connection(self) -> None:
        client = ResumatClient("/dev/null")
        packets: list[bytes] = []
        receive_lengths: list[int] = []

        async def connect() -> None:
            return None

        async def send(packet: bytes) -> None:
            packets.append(packet)

        async def receive(length: int) -> bytes:
            receive_lengths.append(length)
            return bytes(length)

        client._async_connect = connect
        client._async_send_read_request = send
        client._async_receive = receive
        original_interval = PROTOCOL.MIN_READ_REQUEST_INTERVAL
        PROTOCOL.MIN_READ_REQUEST_INTERVAL = 0
        try:
            await client.async_read_data()
            await client.async_read_data()
        finally:
            PROTOCOL.MIN_READ_REQUEST_INTERVAL = original_interval

        self.assertEqual(packets.count(WAKEUP_COMMAND), 1)
        self.assertEqual(receive_lengths, [0x00F3, 0x0046, 0x00F3, 0x0046])
        self.assertEqual(
            packets[1:3],
            [
                build_read_command(0x0000, 0x00F3),
                build_read_command(0x00F3, 0x0046),
            ],
        )
        self.assertEqual(
            packets[3:],
            [
                build_read_command(0x0000, 0x00F3),
                build_read_command(0x00F3, 0x0046),
            ],
        )

    def test_read_requests_are_rate_limited(self) -> None:
        """Normal read requests are separated by the configured minimum."""
        asyncio.run(self._async_test_read_requests_are_rate_limited())

    async def _async_test_read_requests_are_rate_limited(self) -> None:
        client = ResumatClient("/dev/null")
        send_times: list[float] = []

        async def send(packet: bytes) -> None:
            if packet != WAKEUP_COMMAND:
                send_times.append(asyncio.get_running_loop().time())

        async def receive(length: int) -> bytes:
            return bytes(length)

        client._async_connect = lambda: asyncio.sleep(0)
        client._async_send_read_request = send
        client._async_receive = receive
        original_interval = PROTOCOL.MIN_READ_REQUEST_INTERVAL
        PROTOCOL.MIN_READ_REQUEST_INTERVAL = 0.01
        try:
            await client.async_read_data()
        finally:
            PROTOCOL.MIN_READ_REQUEST_INTERVAL = original_interval

        self.assertEqual(len(send_times), 2)
        self.assertGreaterEqual(send_times[1] - send_times[0], 0.01)


def make_response(message_type: int, payload: bytes) -> bytes:
    """Build a Node-RED response packet for decoder tests."""
    body = message_type.to_bytes(2, "big") + payload + bytes(5)
    escaped = body.replace(b"\x10", b"\x10\x10")
    return b"\xff\x10\x02" + escaped


if __name__ == "__main__":
    unittest.main()
