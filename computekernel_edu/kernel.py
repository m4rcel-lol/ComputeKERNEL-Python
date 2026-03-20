"""
SIMULATOR: Kernel orchestrator - models the kernel's main entry point and
the global state of all subsystems.

Real kernel: kmain() (or start_kernel() in Linux) is called after early arch
init and is responsible for initializing all subsystems in order.
"""

from .logger import KernelLogger, log as global_log
from .arch import ArchX86_64
from .memory import PhysicalMemoryManager, VirtualMemoryManager, KmallocAllocator, DEFAULT_PHYS_PAGES
from .process import ProcessTable
from .thread import ThreadTable
from .scheduler import Scheduler
from .vfs import VFS
from .device import DeviceRegistry
from .driver import DriverRegistry
from .boot import BootPipeline
from .profiles import KernelProfile, PROFILES, DEBUG_PROFILE
from .safe_mode import SafeMode
from .module_loader import ModuleLoader, make_default_modules
from .ipc import IpcManager
from .security import CredentialManager
from .power import PowerManager
from .console import SerialConsole, Tty
from .teaching import TeachingEngine
from .panic import KernelPanic


class KernelState:
    """SIMULATOR: Global kernel state - holds references to all subsystems.

    In a real kernel, these would be global variables or per-CPU data in kernel space.
    Here they are attributes of this Python object.
    """

    def __init__(self):
        """SIMULATOR: Create an uninitialized kernel state. Call init() to set up."""
        self.booted:  bool          = False
        self.profile: KernelProfile = DEBUG_PROFILE
        self.logger:  KernelLogger  = global_log

        # Subsystems (initialized in init())
        self.arch:            ArchX86_64            | None = None
        self.pmm:             PhysicalMemoryManager  | None = None
        self.vmm:             VirtualMemoryManager   | None = None
        self.kmalloc:         KmallocAllocator       | None = None
        self.process_table:   ProcessTable           | None = None
        self.thread_table:    ThreadTable            | None = None
        self.scheduler:       Scheduler              | None = None
        self.vfs:             VFS                    | None = None
        self.device_registry: DeviceRegistry         | None = None
        self.driver_registry: DriverRegistry         | None = None
        self.module_loader:   ModuleLoader           | None = None
        self.ipc:             IpcManager             | None = None
        self.cred_mgr:        CredentialManager      | None = None
        self.power:           PowerManager           | None = None
        self.console:         SerialConsole          | None = None
        self.tty:             Tty                    | None = None
        self.safe_mode:       SafeMode               | None = None
        self.boot_pipeline:   BootPipeline           | None = None
        self.teach:           TeachingEngine                = TeachingEngine()

        self._init_complete = False

    def init(self, profile: KernelProfile | None = None):
        """SIMULATOR: Initialize all kernel subsystems. Analog of start_kernel().

        Creates all subsystem objects and wires them together, then creates
        the BootPipeline. Does NOT run the boot sequence - call boot() for that.
        """
        if profile:
            self.profile = profile

        log = self.logger
        log.info("KERN", f"KernelState.init(): profile={self.profile.name}")

        # Disable debug logging if not debug profile
        log._serial_sink = self.profile.serial_log

        self.arch            = ArchX86_64(log)
        self.pmm             = PhysicalMemoryManager(DEFAULT_PHYS_PAGES, log)
        self.vmm             = VirtualMemoryManager(self.pmm, log)
        self.kmalloc         = KmallocAllocator(log)
        self.process_table   = ProcessTable()
        self.thread_table    = ThreadTable(log)
        self.scheduler       = Scheduler(log)
        self.vfs             = VFS(log)
        self.device_registry = DeviceRegistry(log)
        self.driver_registry = DriverRegistry(log)
        self.module_loader   = ModuleLoader(log, self.profile)
        self.ipc             = IpcManager(log)
        self.cred_mgr        = CredentialManager()
        self.power           = PowerManager(log)
        self.console         = SerialConsole(log)
        self.tty             = Tty("tty0", self.console, log)
        self.safe_mode       = SafeMode(self.profile, log)

        # Register default modules
        for mod in make_default_modules():
            self.module_loader.register(mod)

        self.boot_pipeline = BootPipeline(
            logger=log,
            arch=self.arch,
            memory=(self.pmm, self.vmm, self.kmalloc),
            scheduler=self.scheduler,
            vfs=self.vfs,
            device_registry=self.device_registry,
            driver_registry=self.driver_registry,
            process_table=self.process_table,
            profile=self.profile,
            thread_table=self.thread_table,
        )

        self._init_complete = True
        log.info("KERN", "KernelState initialized. Call boot() to run boot sequence.")

    def boot(self) -> bool:
        """SIMULATOR: Run the full boot sequence."""
        if not self._init_complete:
            self.init()
        success = self.boot_pipeline.run_all()
        self.booted = success
        return success

    def boot_step(self):
        """SIMULATOR: Run the next boot stage."""
        if not self._init_complete:
            self.init()
        return self.boot_pipeline.step()

    def status(self) -> dict:
        """SIMULATOR: Return current kernel status summary."""
        return {
            "booted":           self.booted,
            "profile":          self.profile.name,
            "safe_mode":        self.safe_mode.active if self.safe_mode else False,
            "processes":        len(self.process_table.all()) if self.process_table else 0,
            "threads":          len(self.thread_table.all()) if self.thread_table else 0,
            "free_pages":       self.pmm.free_pages if self.pmm else 0,
            "total_pages":      self.pmm.total_pages if self.pmm else 0,
            "scheduler_ticks":  self.scheduler.tick_count if self.scheduler else 0,
            "modules_loaded":   len(self.module_loader.list_loaded()) if self.module_loader else 0,
        }


def kmain(profile_name: str = "debug") -> KernelState:
    """SIMULATOR: Kernel main entry point analog (start_kernel() in Linux).

    In a real kernel, kmain/start_kernel() is called after the bootloader hands
    off control and early arch initialization completes.
    Here it creates and boots a KernelState.
    """
    profile = PROFILES.get(profile_name, DEBUG_PROFILE)
    kernel = KernelState()
    kernel.init(profile)
    kernel.boot()
    return kernel
