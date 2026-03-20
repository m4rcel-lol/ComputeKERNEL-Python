"""
SIMULATOR: Power management subsystem.
Models power state transitions.

Real kernel: Power management involves ACPI state machine (S0=running, S3=suspend-to-RAM,
S4=hibernate, S5=soft-off), driver suspend/resume callbacks, CPU idle states (C-states).
"""

from enum import Enum
from .logger import KernelLogger


class PowerState(Enum):
    """SIMULATOR: System power states (ACPI Sx states conceptually)."""
    RUNNING   = "S0"      # fully on
    SUSPEND   = "S3"      # suspend to RAM
    HIBERNATE = "S4"      # suspend to disk
    SHUTDOWN  = "S5"      # soft off
    REBOOT    = "REBOOT"  # system reboot


class PowerManager:
    """SIMULATOR: Kernel power manager.

    In a real kernel, the power manager coordinates ACPI, driver callbacks,
    CPU power states, and system suspend/resume. Here we just track state.
    """

    def __init__(self, logger: KernelLogger):
        """SIMULATOR: Create a power manager starting in the RUNNING state."""
        self._logger = logger
        self.state = PowerState.RUNNING
        self._transitions: list = []

    def _transition(self, new_state: PowerState, reason: str = ""):
        """SIMULATOR: Perform a power state transition."""
        old = self.state
        self.state = new_state
        self._transitions.append((old, new_state, reason))
        self._logger.info("KERN", f"power: {old.value} -> {new_state.value} ({reason})")

    def suspend(self):
        """SIMULATOR: Enter suspend-to-RAM (S3).

        Real kernel: kernel_suspend() -> pm_suspend(PM_SUSPEND_MEM) ->
        suspend_devices_and_enter() -> platform_suspend_begin() -> CPU offline.
        """
        self._transition(PowerState.SUSPEND, "suspend requested")

    def resume(self):
        """SIMULATOR: Resume from suspend.

        Real kernel: Resume path reverses suspend: CPU online -> platform wakeup ->
        resume devices -> restore PM clocks.
        """
        if self.state == PowerState.SUSPEND:
            self._transition(PowerState.RUNNING, "resume from S3")
        else:
            self._logger.warn("KERN", f"power: resume called in state {self.state.value}")

    def shutdown(self):
        """SIMULATOR: Initiate system shutdown (S5).

        Real kernel: kernel_power_off() -> pm_power_off() -> ACPI S5 transition.
        """
        self._transition(PowerState.SHUTDOWN, "shutdown requested")

    def reboot(self):
        """SIMULATOR: Initiate system reboot.

        Real kernel: kernel_restart() -> machine_restart() -> ACPI reset or
        keyboard controller reset (0xFE to port 0x64).
        """
        self._transition(PowerState.REBOOT, "reboot requested")

    def status(self) -> dict:
        """SIMULATOR: Return current power management status."""
        return {
            "current_state": self.state.value,
            "state_name":    self.state.name,
            "transitions":   len(self._transitions),
        }
