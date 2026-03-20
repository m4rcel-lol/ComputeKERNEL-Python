"""
SIMULATOR: Driver framework.
Models the kernel's driver model - driver registration, device probing, and binding.

Real kernel: Drivers register themselves with a bus (pci_register_driver,
platform_driver_register, etc.). When a new device appears on the bus, the kernel
calls each driver's .probe() callback until one claims the device.
The binding is recorded in the device's driver field.

SIMULATOR: We model driver registration and probe/bind logic in Python.
"""

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional
from .device import Device, DeviceRegistry
from .logger import KernelLogger


@dataclass
class Driver:
    """SIMULATOR: Kernel device driver descriptor (struct device_driver analog).

    Real kernel: struct device_driver contains the driver name, bus type,
    .probe() / .remove() / .suspend() / .resume() callbacks, and module pointer.
    The probe() function is called when the kernel tries to bind a device to a driver.
    """
    name:         str
    description:  str
    supported_devices: List[str] = field(default_factory=list)  # device name patterns
    probe:        Optional[Callable[[Device], bool]] = field(default=None, repr=False)
    is_loaded:    bool = False
    bound_devices: List[str] = field(default_factory=list)

    def default_probe(self, device: Device) -> bool:
        """SIMULATOR: Default probe - matches by device name in supported_devices list."""
        return device.name in self.supported_devices


class DriverRegistry:
    """SIMULATOR: Driver registry (models the kernel's driver core).

    Maintains a list of registered drivers and handles device-driver binding
    via the probe mechanism.
    """

    def __init__(self, logger: KernelLogger):
        """SIMULATOR: Create an empty driver registry."""
        self._logger = logger
        self._drivers: Dict[str, Driver] = {}

    def register(self, driver: Driver):
        """SIMULATOR: Register a driver with the driver core.

        Real kernel: __driver_register() -> bus->drv_groups, sysfs entries,
        and triggers binding against all unbound devices on the bus.
        """
        if driver.name in self._drivers:
            self._logger.warn("DRV", f"register: driver '{driver.name}' already registered")
            return
        driver.is_loaded = True
        self._drivers[driver.name] = driver
        self._logger.info("DRV", f"registered driver: '{driver.name}' ({driver.description})")

    def unregister(self, name: str) -> bool:
        """SIMULATOR: Unregister a driver.

        Real kernel: driver_unregister() unbinds all devices, removes sysfs entries.
        """
        drv = self._drivers.pop(name, None)
        if drv:
            drv.is_loaded = False
            self._logger.info("DRV", f"unregistered driver: '{name}'")
            return True
        self._logger.warn("DRV", f"unregister: driver '{name}' not found")
        return False

    def probe_device(self, device: Device) -> Optional[Driver]:
        """SIMULATOR: Try to find a driver for a device via probe.

        Real kernel: __device_attach() iterates all drivers on the bus and
        calls driver_match_device() then driver->probe(). The first driver
        that returns 0 (success) from probe() claims the device.
        SIMULATOR: We call each driver's probe function or use default name matching.
        """
        for driver in self._drivers.values():
            # Use custom probe if provided, otherwise default name matching
            probe_fn = driver.probe if driver.probe else driver.default_probe
            try:
                if probe_fn(device):
                    self._logger.info("DRV", f"probe: '{driver.name}' claims '{device.name}'")
                    return driver
            except Exception as e:
                self._logger.warn("DRV", f"probe: '{driver.name}' raised {e} for '{device.name}'")
        self._logger.debug("DRV", f"probe: no driver found for '{device.name}'")
        return None

    def bind(self, driver_name: str, device: Device,
             device_registry: DeviceRegistry) -> bool:
        """SIMULATOR: Bind a driver to a device.

        Real kernel: really_probe() - calls driver->probe(), on success sets
        dev->driver and calls driver_bound().
        """
        drv = self._drivers.get(driver_name)
        if drv is None:
            self._logger.warn("DRV", f"bind: driver '{driver_name}' not found")
            return False
        if device.name not in drv.bound_devices:
            drv.bound_devices.append(device.name)
        device_registry.bind_driver(device.name, driver_name)
        self._logger.info("DRV", f"bound: driver='{driver_name}' device='{device.name}'")
        return True

    def remove(self, driver_name: str, device_name: str,
               device_registry: DeviceRegistry) -> bool:
        """SIMULATOR: Unbind a driver from a device (driver->remove() analog)."""
        drv = self._drivers.get(driver_name)
        if drv is None:
            return False
        if device_name in drv.bound_devices:
            drv.bound_devices.remove(device_name)
        dev = device_registry.get(device_name)
        if dev:
            dev.bound_driver = ""
        self._logger.info("DRV", f"removed: driver='{driver_name}' device='{device_name}'")
        return True

    def get(self, name: str) -> Optional[Driver]:
        """SIMULATOR: Look up a driver by name."""
        return self._drivers.get(name)

    def list_all(self) -> List[Driver]:
        """SIMULATOR: Return all registered drivers."""
        return list(self._drivers.values())

    def probe_all(self, device_registry: DeviceRegistry):
        """SIMULATOR: Probe all registered devices against all registered drivers.

        Real kernel: This is triggered during bus enumeration (e.g. PCI scan)
        and when new drivers are loaded (insmod).
        """
        self._logger.info("DRV", "probe_all: matching devices to drivers...")
        for device in device_registry.list_all():
            if not device.bound_driver:
                drv = self.probe_device(device)
                if drv:
                    self.bind(drv.name, device, device_registry)
