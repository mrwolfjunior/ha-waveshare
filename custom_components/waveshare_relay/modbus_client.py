"""Modbus RTU over TCP raw client for Waveshare Relay boards.

Builds Modbus RTU frames manually (no external library required) and
communicates over a persistent asyncio TCP connection to the Ethernet bridge.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CRC16 Modbus helpers
# ---------------------------------------------------------------------------

def crc16_modbus(data: bytes) -> bytes:
    """Return the 2-byte Modbus CRC16 in little-endian order."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return bytes([crc & 0xFF, (crc >> 8) & 0xFF])


def _build_fc05_frame(slave: int, address: int, value: int) -> bytes:
    """Build a Modbus FC05 (Write Single Coil/Register) frame."""
    payload = bytes([
        slave,
        0x05,
        (address >> 8) & 0xFF,
        address & 0xFF,
        (value >> 8) & 0xFF,
        value & 0xFF,
    ])
    return payload + crc16_modbus(payload)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class WaveshareModbusClient:
    """Asynchronous Modbus RTU over TCP client.

    Maintains a single persistent TCP connection to the Ethernet/RS485 bridge.
    All operations are serialised with an asyncio Lock to prevent frame
    collisions on the shared RS485 bus.
    """

    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open TCP connection (raises on failure)."""
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self._host, self._port),
            timeout=10,
        )
        _LOGGER.debug("Connected to %s:%s", self._host, self._port)

    async def disconnect(self) -> None:
        """Close the TCP connection gracefully."""
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass
        self._reader = None
        self._writer = None

    async def _ensure_connected(self) -> None:
        if self._writer is None or self._writer.is_closing():
            await self.connect()

    # ------------------------------------------------------------------
    # Internal send/receive
    # ------------------------------------------------------------------

    async def _send_recv(self, frame: bytes, expected_len: int) -> Optional[bytes]:
        """Send a frame and read the response; auto-reconnect on error."""
        async with self._lock:
            for attempt in range(2):
                try:
                    await self._ensure_connected()
                    self._writer.write(frame)
                    await self._writer.drain()
                    
                    head = await asyncio.wait_for(
                        self._reader.readexactly(3),
                        timeout=5,
                    )
                    
                    fc = head[1]
                    if fc & 0x80:
                        tail_len = 2
                    elif fc in (1, 2, 3, 4):
                        tail_len = 2 + head[2]
                    elif fc in (5, 6, 15, 16):
                        tail_len = 5
                    else:
                        tail_len = max(0, expected_len - 3)
                        
                    if tail_len > 0:
                        tail = await asyncio.wait_for(
                            self._reader.readexactly(tail_len),
                            timeout=5,
                        )
                    else:
                        tail = b""
                        
                    return head + tail
                except Exception as exc:  # noqa: BLE001
                    _LOGGER.warning(
                        "Modbus error (attempt %d): %s", attempt + 1, exc
                    )
                    await self.disconnect()
                    if attempt == 1:
                        return None
        return None

    # ------------------------------------------------------------------
    # Public Modbus commands
    # ------------------------------------------------------------------

    async def flash_on(self, slave: int, relay_index: int, pulse_ms: int) -> bool:
        """FC05 Flash ON — relay activates then auto-deactivates after pulse_ms.

        Address space 0x0200..0x021F (relay 0..31).
        Value = duration in units of 100 ms.
        """
        duration = max(1, pulse_ms // 100)
        address = 0x0200 + (relay_index & 0x1F)
        frame = _build_fc05_frame(slave, address, duration)
        resp = await self._send_recv(frame, 8)
        ok = resp is not None and len(resp) >= 6 and not (resp[1] & 0x80)
        if not ok:
            _LOGGER.error("flash_on relay=%d failed", relay_index)
        return ok

    async def flash_off(self, slave: int, relay_index: int, pulse_ms: int) -> bool:
        """FC05 Flash OFF — relay deactivates then auto-activates after pulse_ms.

        Address space 0x0400..0x041F.
        """
        duration = max(1, pulse_ms // 100)
        address = 0x0400 + (relay_index & 0x1F)
        frame = _build_fc05_frame(slave, address, duration)
        resp = await self._send_recv(frame, 8)
        ok = resp is not None and len(resp) >= 6 and not (resp[1] & 0x80)
        if not ok:
            _LOGGER.error("flash_off relay=%d failed", relay_index)
        return ok

    async def relay_on(self, slave: int, relay_index: int) -> bool:
        """FC05 — permanently turn relay ON."""
        frame = _build_fc05_frame(slave, relay_index & 0x1F, 0xFF00)
        resp = await self._send_recv(frame, 8)
        return resp is not None and len(resp) >= 6 and not (resp[1] & 0x80)

    async def relay_off(self, slave: int, relay_index: int) -> bool:
        """FC05 — permanently turn relay OFF."""
        frame = _build_fc05_frame(slave, relay_index & 0x1F, 0x0000)
        resp = await self._send_recv(frame, 8)
        return resp is not None and len(resp) >= 6 and not (resp[1] & 0x80)

    async def read_coils(
        self, slave: int, start: int, count: int
    ) -> Optional[list[bool]]:
        """FC01 — Read coil (relay) status.

        Returns list of booleans, index 0 = relay 0.
        """
        payload = bytes([
            slave, 0x01,
            (start >> 8) & 0xFF, start & 0xFF,
            (count >> 8) & 0xFF, count & 0xFF,
        ])
        frame = payload + crc16_modbus(payload)
        byte_count = (count + 7) // 8
        resp = await self._send_recv(frame, 3 + byte_count + 2)
        if resp is None or len(resp) < 3 or (resp[1] & 0x80):
            return None
        data_len = resp[2]
        data_bytes = resp[3: 3 + data_len]
        result: list[bool] = []
        for i in range(count):
            b = i // 8
            bit = i % 8
            result.append(bool(data_bytes[b] & (1 << bit)) if b < len(data_bytes) else False)
        return result

    async def read_discrete_inputs(
        self, slave: int, start: int, count: int
    ) -> Optional[list[bool]]:
        """Read discrete inputs (FC02). Returns a list of booleans."""
        payload = bytes(
            [
                slave,
                0x02,
                (start >> 8) & 0xFF,
                start & 0xFF,
                (count >> 8) & 0xFF,
                count & 0xFF,
            ]
        )
        frame = payload + crc16_modbus(payload)

        # FC02 response: Slave(1) + FC(1) + ByteCount(1) + Data(ByteCount) + CRC(2)
        # We calculate the expected maximum length just to be safe, but _send_recv
        # uses the ByteCount field dynamically anyway.
        expected_len = 3 + ((count + 7) // 8) + 2

        resp = await self._send_recv(frame, expected_len)
        if resp is None or len(resp) < 3 or (resp[1] & 0x80):
            return None

        data_len = resp[2]
        data_bytes = resp[3 : 3 + data_len]
        
        result: list[bool] = []
        for i in range(count):
            byte_idx = i // 8
            bit_idx = i % 8
            if byte_idx < len(data_bytes):
                result.append(bool(data_bytes[byte_idx] & (1 << bit_idx)))
            else:
                result.append(False)
        return result

    async def read_holding_registers(
        self, slave: int, start: int, count: int
    ) -> Optional[list[int]]:
        """FC03 — Read holding registers.

        Returns list of 16-bit unsigned integers.
        """
        payload = bytes([
            slave, 0x03,
            (start >> 8) & 0xFF, start & 0xFF,
            (count >> 8) & 0xFF, count & 0xFF,
        ])
        frame = payload + crc16_modbus(payload)
        resp = await self._send_recv(frame, 3 + count * 2 + 2)
        if resp is None or len(resp) < 3 or (resp[1] & 0x80):
            return None
        data_len = resp[2]
        data_bytes = resp[3: 3 + data_len]
        result: list[int] = []
        for i in range(0, len(data_bytes) - 1, 2):
            result.append((data_bytes[i] << 8) | data_bytes[i + 1])
        return result

    async def write_multiple_coils(
        self, slave: int, start: int, coils: list[bool]
    ) -> bool:
        """FC0F — Write multiple coils simultaneously."""
        count = len(coils)
        byte_count = (count + 7) // 8
        coil_bytes = bytearray(byte_count)
        for i, coil in enumerate(coils):
            if coil:
                coil_bytes[i // 8] |= 1 << (i % 8)
        payload = bytes([
            slave, 0x0F,
            (start >> 8) & 0xFF, start & 0xFF,
            (count >> 8) & 0xFF, count & 0xFF,
            byte_count,
        ]) + bytes(coil_bytes)
        frame = payload + crc16_modbus(payload)
        resp = await self._send_recv(frame, 8)
        return resp is not None and len(resp) >= 6 and not (resp[1] & 0x80)
