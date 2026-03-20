"""
SIMULATOR: Serial console and TTY subsystem.
Models the kernel's serial console (COM1/UART) and TTY layer.

Real kernel: The serial console is one of the first things initialized because
it works before any other output mechanism. Writes go directly to UART I/O ports
(0x3F8 for COM1). The TTY layer adds line discipline (echo, canonical mode, signals).

SIMULATOR: We just print to Python stdout, but model the concepts.
"""

import sys
from collections import deque
from .logger import KernelLogger


class SerialConsole:
    """SIMULATOR: Models a UART serial console (COM1 / 0x3F8).

    In a real kernel, the serial console driver writes bytes to I/O port 0x3F8
    (or memory-mapped UART registers). This is used for early boot messages
    before any framebuffer or VGA console is available.
    """

    def __init__(self, logger: KernelLogger, port: str = "COM1"):
        """SIMULATOR: Initialize the serial console model."""
        self._logger = logger
        self.port = port
        self._rx_buffer: deque = deque(maxlen=256)
        self._tx_count = 0
        self._enabled = True

    def write(self, data: bytes):
        """SIMULATOR: Write bytes to the simulated serial console."""
        if not self._enabled:
            return
        text = data.decode("utf-8", errors="replace")
        sys.stdout.write(text)
        sys.stdout.flush()
        self._tx_count += len(data)

    def writeline(self, text: str):
        """SIMULATOR: Write a line to the serial console."""
        self.write((text + "\n").encode())

    def receive(self, data: bytes):
        """SIMULATOR: Simulate receiving bytes from the UART RX buffer."""
        for b in data:
            self._rx_buffer.append(b)

    def read(self, n: int = 1) -> bytes:
        """SIMULATOR: Read bytes from the RX buffer."""
        result = []
        for _ in range(min(n, len(self._rx_buffer))):
            result.append(self._rx_buffer.popleft())
        return bytes(result)

    def stats(self) -> dict:
        """SIMULATOR: Return serial console statistics."""
        return {
            "port":       self.port,
            "enabled":    self._enabled,
            "tx_bytes":   self._tx_count,
            "rx_pending": len(self._rx_buffer),
        }


class Tty:
    """SIMULATOR: Models a TTY (teletypewriter) device.

    In a real kernel, the TTY layer sits between user-space programs and the
    underlying terminal hardware. It provides line discipline (POSIX termios):
    canonical mode (line buffering, ^C/^Z signal sending), echo, cooked mode.
    """

    def __init__(self, name: str, console: SerialConsole, logger: KernelLogger):
        """SIMULATOR: Create a TTY attached to the given serial console."""
        self.name = name
        self._console = console
        self._logger = logger
        self._canonical = True   # line discipline: canonical mode
        self._echo = True
        self._input_buffer = ""
        self._output_buffer = []

    def write(self, data: str):
        """SIMULATOR: Write data through the TTY to the console."""
        self._console.writeline(data)
        self._output_buffer.append(data)

    def receive_input(self, text: str):
        """SIMULATOR: Receive user input through the TTY line discipline."""
        if self._echo:
            self._console.writeline(text)
        self._input_buffer = text

    def flush(self):
        """SIMULATOR: Flush TTY output buffer."""
        self._output_buffer.clear()
