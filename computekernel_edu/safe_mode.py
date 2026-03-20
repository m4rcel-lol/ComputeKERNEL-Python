"""
SIMULATOR: Safe mode enforcement module.
Models how a kernel's safe/recovery mode restricts subsystems.
"""

from .profiles import KernelProfile
from .logger import KernelLogger


class SafeMode:
    """
    SIMULATOR: Models safe-mode boot restrictions.
    In a real kernel, safe mode (similar to Linux's init=/bin/sh or single-user mode)
    restricts which drivers and modules are loaded to recover from bad states.
    """

    def __init__(self, profile: KernelProfile, logger: KernelLogger):
        self._profile = profile
        self._logger = logger

    @property
    def active(self) -> bool:
        """SIMULATOR: Returns True if currently booting in safe mode."""
        return self._profile.name == "safe_mode"

    def check_module_load(self, module_name: str) -> bool:
        """SIMULATOR: Check whether a module is allowed to load under current profile."""
        if self.active and not self._profile.modules_enabled:
            self._logger.warn("SAFE", f"Safe mode: blocking module load '{module_name}'")
            return False
        return True

    def check_driver_load(self, driver_name: str, is_essential: bool) -> bool:
        """SIMULATOR: Check whether a driver is allowed to load under current profile."""
        if self.active and not self._profile.non_essential_drivers and not is_essential:
            self._logger.warn("SAFE", f"Safe mode: skipping non-essential driver '{driver_name}'")
            return False
        return True

    def report(self) -> dict:
        """SIMULATOR: Return a summary of safe mode status."""
        return {
            "active": self.active,
            "profile": self._profile.name,
            "modules_enabled": self._profile.modules_enabled,
            "non_essential_drivers": self._profile.non_essential_drivers,
            "description": self._profile.description,
        }
