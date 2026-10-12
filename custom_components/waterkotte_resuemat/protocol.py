"""Serial protocol implementation for the Waterkotte Resümat CD4."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
import logging
import math
import struct
from typing import Final

BAUDRATE: Final = 9600
WAKEUP_COMMAND: Final = (
    b"AT "
    + bytes.fromhex(
        "10020115000000041003cb9b03"
        "10020115003000041003cb9de2889a"
        "100201150034000410037dc3aa"
    )
    + bytes(1024)
)
READ_RANGES: Final = (
    (0x0000, 0x00F3),
    (0x00F3, 0x0046),
)
MIN_READ_REQUEST_INTERVAL: Final = 30
RESPONSE_TIMEOUT: Final = 10
READ_RESPONSE: Final = 0x0017
_START: Final = b"\xff\x10\x02"
_RESPONSE_HEADER: Final = _START + READ_RESPONSE.to_bytes(2, "big")
_RESPONSE_OVERHEAD: Final = 10
_READ_MARKER: Final = b"\x10\x03"
_MAX_BUFFER: Final = 8192
_LOGGER = logging.getLogger(__name__)


class ResumatProtocolError(Exception):
    """Raised when the serial protocol returns an invalid frame."""


@dataclass(frozen=True)
class Frame:
    """A decoded protocol frame."""

    message_type: int
    payload: bytes


def crc16(data: bytes) -> int:
    """Calculate the CRC-16/BUYPASS checksum used by the controller."""
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x8005
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc


def _escape(data: bytes) -> bytes:
    """Escape DLE bytes in a frame body."""
    return data.replace(b"\x10", b"\x10\x10")


def _build_command(body: bytes) -> bytes:
    """Build a controller command around its unescaped body."""
    checksum = crc16(body)
    return (
        b"\x10\x02"
        + _escape(body)
        + _READ_MARKER
        + checksum.to_bytes(2, "big")
    )


def build_read_command(address: int, length: int) -> bytes:
    """Build a memory read request."""
    if not 0 <= address <= 0xFFFF or not 1 <= length <= 0xFFFF:
        raise ValueError("Address and length must fit in 16 bits")
    body = b"\x01\x15" + address.to_bytes(2, "big") + length.to_bytes(2, "big")
    return _build_command(body)


class FrameDecoder:
    """Decode Node-RED response packets from a serial byte stream."""

    def __init__(self) -> None:
        """Initialize the stream buffer."""
        self._buffer = bytearray()

    @property
    def pending_data(self) -> bytes:
        """Return buffered bytes that have not formed a complete frame."""
        return bytes(self._buffer)

    def feed(self, data: bytes, expected_length: int) -> list[Frame]:
        """Return complete replies using the expected length and DLE unescaping."""
        self._buffer.extend(data)
        if len(self._buffer) > _MAX_BUFFER:
            del self._buffer[:-len(_RESPONSE_HEADER)]
            raise ResumatProtocolError("Serial response exceeded the frame buffer")

        frames: list[Frame] = []
        expected_frame_length = expected_length + _RESPONSE_OVERHEAD
        while True:
            start = self._buffer.find(_RESPONSE_HEADER)
            if start < 0:
                keep = len(_RESPONSE_HEADER) - 1
                if len(self._buffer) > keep:
                    del self._buffer[:-keep]
                break
            if start:
                del self._buffer[:start]

            response = bytearray(_RESPONSE_HEADER)
            index = len(_RESPONSE_HEADER)
            while (
                index < len(self._buffer)
                and len(response) < expected_frame_length
            ):
                byte = self._buffer[index]
                if byte == 0x10:
                    if index + 1 >= len(self._buffer):
                        break
                    if self._buffer[index + 1] == 0x10:
                        response.append(byte)
                        index += 2
                        continue
                response.append(byte)
                index += 1

            if len(response) < expected_frame_length:
                break

            payload = response[
                len(_RESPONSE_HEADER) : len(_RESPONSE_HEADER) + expected_length
            ]
            frames.append(Frame(READ_RESPONSE, bytes(payload)))
            del self._buffer[:index]

        return frames


class ResumatClient:
    """Manage serial communication and decode current heat-pump data."""

    def __init__(self, port: str) -> None:
        """Initialize a serial client."""
        self.port = port
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._decoder = FrameDecoder()
        self._lock = asyncio.Lock()
        self._wakeup_sent = False
        self._last_read_request_at: float | None = None
        self.status = "disconnected"
        self.last_error: str | None = None
        self._status_callback: Callable[[], None] | None = None

    def set_status_callback(self, callback: Callable[[], None]) -> None:
        """Register a callback for communication status changes."""
        self._status_callback = callback

    def set_status(self, status: str, error: str | None = None) -> None:
        """Update communication status and notify Home Assistant entities."""
        if status == self.status and error == self.last_error:
            return
        _LOGGER.debug("Serial status: %s%s", status, f": {error}" if error else "")
        self.status = status
        self.last_error = error
        if self._status_callback is not None:
            self._status_callback()

    def close(self) -> None:
        """Close an open serial connection."""
        if self._writer is not None:
            self._writer.close()
        self._reader = None
        self._writer = None
        self._decoder = FrameDecoder()
        self._wakeup_sent = False
        if self.status != "error":
            self.set_status("disconnected")

    async def _async_connect(self) -> None:
        """Open the serial port if needed."""
        if self._writer is not None and not self._writer.is_closing():
            return
        self.set_status("connecting")
        import serialx

        self._reader, self._writer = await serialx.open_serial_connection(
            url=self.port,
            baudrate=BAUDRATE,
            bytesize=8,
            parity="N",
            stopbits=1,
        )
        self._decoder = FrameDecoder()
        self._wakeup_sent = False

    async def _async_wake_if_needed(self) -> None:
        """Unlock each newly opened serial connection without awaiting a reply."""
        await self._async_connect()
        if self._wakeup_sent:
            return
        self.set_status("waking")
        await self._async_send_read_request(WAKEUP_COMMAND)
        self._wakeup_sent = True

    async def _async_send_read_request(self, packet: bytes) -> None:
        """Transmit a wake-up or read request only; never write controller values."""
        await self._async_connect()
        assert self._writer is not None
        _LOGGER.debug(
            "Transmitting %d read/wakeup bytes: %s", len(packet), packet.hex()
        )
        self._writer.write(packet)
        await self._writer.drain()

    async def _async_receive(self, expected_length: int) -> bytes:
        """Wait for a read response with the requested data length."""
        assert self._reader is not None
        deadline = asyncio.get_running_loop().time() + RESPONSE_TIMEOUT
        received = bytearray()
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                chunk = b""
            else:
                try:
                    chunk = await asyncio.wait_for(
                        self._reader.read(512), remaining
                    )
                except asyncio.TimeoutError as err:
                    detail = self._response_timeout_detail(
                        expected_length, received
                    )
                    _LOGGER.debug("%s", detail)
                    raise TimeoutError(detail) from err
            if not chunk and remaining <= 0:
                detail = self._response_timeout_detail(expected_length, received)
                _LOGGER.debug("%s", detail)
                raise TimeoutError(detail)
            if not chunk:
                raise OSError("Serial port closed while waiting for a response")
            received.extend(chunk)
            self.set_status("receiving")
            _LOGGER.debug(
                "Received serial chunk (%d bytes): %s",
                len(chunk),
                chunk.hex(),
            )
            for frame in self._decoder.feed(chunk, expected_length):
                _LOGGER.debug(
                    "Decoded frame type 0x%04x with %d payload bytes",
                    frame.message_type,
                    len(frame.payload),
                )
                if frame.message_type != READ_RESPONSE:
                    continue
                if len(frame.payload) < expected_length:
                    _LOGGER.debug(
                        "Ignoring short read response with %d payload bytes; "
                        "expected %d",
                        len(frame.payload),
                        expected_length,
                    )
                    continue
                _LOGGER.debug(
                    "Received complete read response: %d wire bytes, "
                    "%d payload bytes (%s)",
                    len(received),
                    len(frame.payload),
                    received.hex(),
                )
                return frame.payload[:expected_length]

    def _response_timeout_detail(
        self, expected_length: int, received: bytearray
    ) -> str:
        """Describe partial bytes received before a response timeout."""
        pending = self._decoder.pending_data
        received_preview = received[:128].hex()
        suffix = "..." if len(received) > 128 else ""
        return (
            f"Timed out waiting for read response (expected {expected_length} "
            f"payload bytes, received {len(received)} wire bytes; "
            f"decoder buffer: {pending.hex() or 'empty'}; received data: "
            f"{received_preview}{suffix or 'none'})"
        )

    async def _async_read_range(self, address: int, length: int) -> bytes:
        """Request and receive one contiguous address range."""
        if self._last_read_request_at is not None:
            elapsed = asyncio.get_running_loop().time() - self._last_read_request_at
            remaining = MIN_READ_REQUEST_INTERVAL - elapsed
            if remaining > 0:
                await asyncio.sleep(remaining)
        await self._async_wake_if_needed()
        self.set_status("sending_request")
        await self._async_send_read_request(build_read_command(address, length))
        self._last_read_request_at = asyncio.get_running_loop().time()
        self.set_status("waiting_response")
        return await self._async_receive(length)

    async def async_read_data(self) -> dict[str, float | bool | None]:
        """Read controller memory using read requests only."""
        async with self._lock:
            await self._async_wake_if_needed()
            data = bytearray()
            for address, length in READ_RANGES:
                data.extend(await self._async_read_range(address, length))
            self.set_status("parsing")
            readings = decode_readings(data)
            self.set_status("idle")
            return readings


def _float_at(data: bytes | bytearray, address: int) -> float | None:
    """Read a little-endian float at a controller memory address."""
    value = struct.unpack_from("<f", data, address)[0]
    return value if math.isfinite(value) else None


def decode_readings(data: bytes | bytearray) -> dict[str, float | bool | None]:
    """Decode values exposed by the Node-RED flow."""
    if len(data) < sum(length for _, length in READ_RANGES):
        raise ResumatProtocolError("Combined read data is shorter than expected")

    return {
        "outdoor_temperature": _float_at(data, 0x0008),
        "outdoor_temperature_24h": _float_at(data, 0x000C),
        "return_temperature_target": _float_at(data, 0x0014),
        "return_temperature": _float_at(data, 0x0018),
        "flow_temperature": _float_at(data, 0x001C),
        "hot_water_setpoint": _float_at(data, 0x0020),
        "hot_water_temperature": _float_at(data, 0x0024),
        "source_inlet_temperature": _float_at(data, 0x0030),
        "source_outlet_temperature": _float_at(data, 0x0034),
        "compressor_operating_hours": _float_at(data, 0x006A),
        "heating_operating_hours": _float_at(data, 0x006E),
        "hot_water_operating_hours": _float_at(data, 0x0072),
        "heating_setpoint": _float_at(data, 0x00F8),
        "heating_start_temperature": _float_at(data, 0x00F4),
        "heating_disabled": bool(data[0x00F3] & 0x01),
        "hot_water_disabled": bool(data[0x0134] & 0x01),
        "heating_running": bool(data[0x00DF] & 0x01),
        "hot_water_running": bool(data[0x00E1] & 0x01),
    }
