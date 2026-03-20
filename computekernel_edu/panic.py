"""
SIMULATOR: Kernel panic mechanism.
Models the unrecoverable kernel error path (panic()).
"""

import traceback
from .logger import KernelLogger


PANIC_BANNER = """
================================================================================
                        *** SIMULATED KERNEL PANIC ***
  ComputeKERNEL-Edu: This is a simulated panic for educational purposes.
  In a real kernel, this would halt all CPUs and display a crash report.
================================================================================
"""


class KernelPanic(Exception):
    """SIMULATOR: Models a kernel panic - an unrecoverable kernel error.

    In a real kernel, panic() disables interrupts, halts other CPUs via IPI,
    optionally dumps a stack trace, and locks up the machine (or reboots if
    panic_on_oops/panic_timeout is configured).
    """
    def __init__(self, message: str, subsystem: str = "KERN"):
        self.subsystem = subsystem
        super().__init__(message)


def panic(message: str, subsystem: str = "KERN", logger: KernelLogger | None = None):
    """SIMULATOR: Trigger a simulated kernel panic with crash report.

    Real kernel analog: panic() in kernel/panic.c - disables interrupts,
    prints oops message, optionally triggers kdump, halts or reboots.
    """
    print(PANIC_BANNER)
    report = [
        f"Panic in [{subsystem}]: {message}",
        "Simulated call trace:",
    ]
    for line in traceback.format_stack()[:-1]:
        report.append(line.rstrip())

    crash_report = "\n".join(report)
    print(crash_report)

    if logger:
        logger.panic(subsystem, f"PANIC: {message}")

    raise KernelPanic(message, subsystem)
