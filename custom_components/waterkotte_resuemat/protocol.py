"""Serial protocol implementation for the Waterkotte Resümat CD4."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import math
import struct
from typing import Final

BAUDRATE: Final = 9600
READ_RANGES: Final = (
    (0x0000, 0x00F3),
    (0x00F3, 0x0046),
    (0x0139, 0x0006),
)
RESPONSE_TIMEOUT: Final = 10
READ_RESPONSE: Final = 0x0017
_START: Final = b"\x16\x10\x02"
_READ_MARKER: Final = b"\x10\x03"
_MAX_BUFFER: Final = 8192


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


def build_write_command(address: int, value: bytes) -> bytes:
    """Build a memory write request."""
    if not 0 <= address <= 0xFFFF or not value:
        raise ValueError("Address must fit in 16 bits and value cannot be empty")
    body = b"\x01\x13" + address.to_bytes(2, "big") + value
    return _build_command(body)


class FrameDecoder:
    """Decode and checksum response frames from a serial byte stream."""

    def __init__(self) -> None:
        """Initialize the stream buffer."""
        self._buffer = bytearray()

    def feed(self, data: bytes) -> list[Frame]:
        """Append bytes and return all complete frames."""
        self._buffer.extend(data)
        if len(self._buffer) > _MAX_BUFFER:
            del self._buffer[:-len(_START)]
            raise ResumatProtocolError("Serial response exceeded the frame buffer")

        frames: list[Frame] = []
        while True:
            start = self._buffer.find(_START)
            if start < 0:
                keep = len(_START) - 1
                if len(self._buffer) > keep:
                    del self._buffer[:-keep]
                break
            if start:
                del self._buffer[:start]

            body = bytearray()
            index = len(_START)
            complete = False
            while index < len(self._buffer):
                byte = self._buffer[index]
                if byte != 0x10:
                    body.append(byte)
                    index += 1
                    continue
                if index + 1 >= len(self._buffer):
                    break
                following = self._buffer[index + 1]
                if following == 0x10:
                    body.append(0x10)
                    index += 2
                    continue
                if following == 0x03:
                    if len(self._buffer) < index + 5:
                        break
                    checksum = int.from_bytes(
                        self._buffer[index + 2 : index + 4], "big"
                    )
                    if self._buffer[index + 4] != 0x16:
                        del self._buffer[0]
                        complete = True
                        break
                    del self._buffer[: index + 5]
                    complete = True
                    if len(body) < 2:
                        raise ResumatProtocolError("Response frame has no message type")
                    if crc16(body) != checksum:
                        raise ResumatProtocolError("Response frame has an invalid CRC")
                    frames.append(
                        Frame(int.from_bytes(body[:2], "big"), bytes(body[2:]))
                    )
                    break
                body.append(byte)
                index += 1

            if not complete:
                break

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

    def close(self) -> None:
        """Close an open serial connection."""
        if self._writer is not None:
            self._writer.close()
        self._reader = None
        self._writer = None
        self._decoder = FrameDecoder()

    async def _async_connect(self) -> None:
        """Open the serial port if needed."""
        if self._writer is not None and not self._writer.is_closing():
            return
        import serial_asyncio

        self._reader, self._writer = await serial_asyncio.open_serial_connection(
            url=self.port,
            baudrate=BAUDRATE,
            bytesize=8,
            parity="N",
            stopbits=1,
        )
        self._decoder = FrameDecoder()

    async def _async_send(self, packet: bytes) -> None:
        """Write bytes to the controller."""
        await self._async_connect()
        assert self._writer is not None
        self._writer.write(packet)
        await self._writer.drain()

    async def _async_receive(self, expected_length: int) -> bytes:
        """Wait for a read response with the requested data length."""
        assert self._reader is not None
        deadline = asyncio.get_running_loop().time() + RESPONSE_TIMEOUT
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError("Timed out waiting for a controller response")
            chunk = await asyncio.wait_for(self._reader.read(512), remaining)
            if not chunk:
                raise OSError("Serial port closed while waiting for a response")
            for frame in self._decoder.feed(chunk):
                if frame.message_type != READ_RESPONSE:
                    continue
                if len(frame.payload) < expected_length:
                    raise ResumatProtocolError(
                        f"Read response contains {len(frame.payload)} bytes; "
                        f"expected {expected_length}"
                    )
                return frame.payload[:expected_length]

    async def _async_read_range(self, address: int, length: int) -> bytes:
        """Request and receive one contiguous address range."""
        await self._async_send(build_read_command(address, length))
        return await self._async_receive(length)

    async def async_read_data(self) -> dict[str, float | bool | None]:
        """Read the ranges used by the Node-RED flow and setpoint control."""
        async with self._lock:
            await self._async_connect()
            await self._async_send(b"AT ")
            data = bytearray()
            for address, length in READ_RANGES:
                data.extend(await self._async_read_range(address, length))
            return decode_readings(data)

    async def async_write_float(self, address: int, value: float) -> None:
        """Write a little-endian float setpoint."""
        if not math.isfinite(value):
            raise ValueError("Setpoint must be a finite number")
        async with self._lock:
            await self._async_send(
                build_write_command(address, struct.pack("<f", value))
            )

    async def async_write_enabled(self, address: int, enabled: bool) -> None:
        """Write an enabled flag (zero means enabled in the controller)."""
        async with self._lock:
            await self._async_send(
                build_write_command(address, bytes((0 if enabled else 1,)))
            )


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
        "hot_water_setpoint": _float_at(data, 0x013B),
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
