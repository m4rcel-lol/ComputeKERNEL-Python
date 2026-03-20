"""
SIMULATOR: Device registry subsystem.
Models the kernel device model (sysfs / kobject / bus / driver binding).

Real kernel: The device model (drivers/base/) provides a unified representation
of all devices. Devices are organized in a hierarchy (bus -> device -> driver).
sysfs (/sys) exposes this hierarchy to userspace.

SIMULATOR: We use Python dataclasses and a dict for educational modeling.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional
from .logger import KernelLogger


class DeviceClass(Enum):
    """SIMULATOR: Device classes (analogous to Linux device classes in /sys/class/)."""
    CHAR      = auto()   # character device (tty, input, etc.)
    BLOCK     = auto()   # block device (disk, partition)
    NETWORK   = auto()   # network interface
    BUS       = auto()   # bus (PCI, USB, I2C)
    PLATFORM  = auto()   # platform device (non-enumerable, device tree)
    VIRTUAL   = auto()   # virtual device (loop, null, zero)
    INPUT     = auto()   # input device (keyboard, mouse)
    TIMER     = auto()   # timer/clock device


@dataclass
class Device:
    """SIMULATOR: Represents a kernel device (struct device analog).

    Real kernel: struct device contains kobject (ref-counted kernel object),
    bus_type pointer, driver pointer, device_type, power management state,
    parent device, and device-specific private data.
    """
    name:        str
    device_class: DeviceClass
    major:       int        = 0
    minor:       int        = 0
    description: str        = ""
    is_virtual:  bool       = False
    bound_driver: str       = ""   # name of the driver currently bound
    properties:  Dict[str, str] = field(default_factory=dict)

    def __repr__(self) -> str:
        return (f"Device(name={self.name!r}, class={self.device_class.name}, "
                f"major={self.major}, minor={self.minor})")


class DeviceRegistry:
    """SIMULATOR: Global device registry (models the kernel's device tree).

    Real kernel: Devices are organized in a tree rooted at the 'root' bus.
    Each bus (PCI, USB, platform) enumerates its devices and registers them.
    The device registry here is a flat dict for simplicity.
    """

    def __init__(self, logger: KernelLogger):
        """SIMULATOR: Create an empty device registry."""
        self._logger = logger
        self._devices: Dict[str, Device] = {}

    def register(self, device: Device):
        """SIMULATOR: Register a device with the kernel device model.

        Real kernel: device_register() -> device_add() -> kobject_add() creates
        the sysfs directory, sends KOBJ_ADD uevent to udevd (userspace device manager).
        The uevent causes udev to create /dev nodes and run device rules.
        """
        if device.name in self._devices:
            self._logger.warn("DEV", f"register: device '{device.name}' already registered")
            return
        self._devices[device.name] = device
        self._logger.info("DEV", (
            f"registered: {device.name} class={device.device_class.name} "
            f"major={device.major} minor={device.minor} desc={device.description!r}"
        ))

    def unregister(self, name: str) -> bool:
        """SIMULATOR: Unregister a device (device_unregister()).

        Real kernel: Sends KOBJ_REMOVE uevent, removes sysfs entries, unbinds driver,
        decrements kobject refcount. When refcount hits zero, device is freed.
        """
        dev = self._devices.pop(name, None)
        if dev:
            self._logger.info("DEV", f"unregistered: {name}")
            return True
        self._logger.warn("DEV", f"unregister: device '{name}' not found")
        return False

    def get(self, name: str) -> Optional[Device]:
        """SIMULATOR: Look up a device by name."""
        return self._devices.get(name)

    def list_all(self) -> List[Device]:
        """SIMULATOR: Return all registered devices."""
        return list(self._devices.values())

    def list_by_class(self, device_class: DeviceClass) -> List[Device]:
        """SIMULATOR: Return devices filtered by class."""
        return [d for d in self._devices.values() if d.device_class == device_class]

    def bind_driver(self, device_name: str, driver_name: str) -> bool:
        """SIMULATOR: Bind a driver to a device.

        Real kernel: driver_bind() calls driver->probe(device). If probe()
        returns 0, the driver/device binding is established. The device's
        driver pointer is set and it appears in sysfs as device/driver -> symlink.
        """
        dev = self._devices.get(device_name)
        if dev is None:
            self._logger.warn("DEV", f"bind_driver: device '{device_name}' not found")
            return False
        dev.bound_driver = driver_name
        self._logger.info("DEV", f"bind: {device_name} <-> driver '{driver_name}'")
        return True
