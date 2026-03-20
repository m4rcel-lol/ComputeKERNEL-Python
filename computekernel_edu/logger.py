"""
SIMULATOR: Kernel logger with ring buffer.
Models the kernel's printk() / dmesg ring buffer mechanism.

Real kernel: printk() writes to an in-kernel ring buffer (typically 512KB–4MB)
accessible via /dev/kmsg and the dmesg(1) command. Messages have a log level
(KERN_EMERG through KERN_DEBUG) and a timestamp.

SIMULATOR: We use a Python deque as the ring buffer and optionally print to stdout.
"""

from dataclasses import dataclass
from datetime import datetime
from collections import deque
from enum import IntEnum
from typing import List


class LogLevel(IntEnum):
    """SIMULATOR: Kernel log levels analogous to Linux's KERN_* levels."""
    DEBUG = 0
    INFO  = 1
    WARN  = 2
    ERROR = 3
    PANIC = 4

    def label(self) -> str:
        return ["DEBUG", "INFO ", "WARN ", "ERROR", "PANIC"][self.value]


@dataclass
class LogEntry:
    """SIMULATOR: A single kernel log entry (like a printk record)."""
    level: LogLevel
    subsystem: str
    message: str
    timestamp: float

    def __str__(self) -> str:
        ts = f"{self.timestamp:10.4f}"
        return f"[{ts}] [{self.level.label()}] [{self.subsystem:<8}] {self.message}"


class KernelLogger:
    """SIMULATOR: Kernel logger with ring buffer.

    Models the Linux printk() infrastructure:
    - Ring buffer (struct printk_ringbuf) that holds recent messages.
    - Log levels (DEBUG, INFO, WARN, ERROR, PANIC).
    - Optional serial sink that mirrors messages to stdout (simulating early console).

    Real kernel: dmesg reads /dev/kmsg which exposes the ring buffer.
    SIMULATOR: get_entries() / dump() provide equivalent access.
    """

    MAX_ENTRIES = 1024

    def __init__(self, serial_sink: bool = True):
        self._ring: deque = deque(maxlen=self.MAX_ENTRIES)
        self._serial_sink = serial_sink
        self._start = datetime.now().timestamp()

    def _elapsed(self) -> float:
        return datetime.now().timestamp() - self._start

    def _log(self, level: LogLevel, subsystem: str, message: str):
        entry = LogEntry(
            level=level,
            subsystem=subsystem,
            message=message,
            timestamp=self._elapsed(),
        )
        self._ring.append(entry)
        if self._serial_sink:
            print(str(entry))

    def debug(self, subsystem: str, message: str):
        """SIMULATOR: Log at DEBUG level (KERN_DEBUG equivalent)."""
        self._log(LogLevel.DEBUG, subsystem, message)

    def info(self, subsystem: str, message: str):
        """SIMULATOR: Log at INFO level (KERN_INFO equivalent)."""
        self._log(LogLevel.INFO, subsystem, message)

    def warn(self, subsystem: str, message: str):
        """SIMULATOR: Log at WARN level (KERN_WARNING equivalent)."""
        self._log(LogLevel.WARN, subsystem, message)

    def error(self, subsystem: str, message: str):
        """SIMULATOR: Log at ERROR level (KERN_ERR equivalent)."""
        self._log(LogLevel.ERROR, subsystem, message)

    def panic(self, subsystem: str, message: str):
        """SIMULATOR: Log at PANIC level (KERN_EMERG equivalent)."""
        self._log(LogLevel.PANIC, subsystem, message)

    def get_entries(self, min_level: LogLevel = LogLevel.DEBUG) -> List[LogEntry]:
        """SIMULATOR: Retrieve log entries at or above the given level (like dmesg -l)."""
        return [e for e in self._ring if e.level >= min_level]

    def dump(self, min_level: LogLevel = LogLevel.DEBUG) -> str:
        """SIMULATOR: Return all matching log entries as a formatted string (dmesg output)."""
        return "\n".join(str(e) for e in self.get_entries(min_level))


# Global logger instance - analogous to the kernel's global printk buffer.
log = KernelLogger()
