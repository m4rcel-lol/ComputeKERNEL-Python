"""
SIMULATOR: Boot pipeline for ComputeKERNEL-Edu.
Models the kernel boot sequence from firmware handoff to userspace init.

Real kernel: The boot sequence involves firmware (BIOS/UEFI), bootloader (GRUB2),
architecture-specific early init, memory manager bringup, scheduler start,
VFS/device init, and finally spawning the init process.

SIMULATOR: We model each stage as a Python method call with detailed logging
explaining what the corresponding real kernel code would do.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, List, Optional, Tuple

from .logger import KernelLogger
from .profiles import KernelProfile

if TYPE_CHECKING:
    from .arch import ArchX86_64
    from .memory import PhysicalMemoryManager, VirtualMemoryManager, KmallocAllocator
    from .scheduler import Scheduler
    from .vfs import VFS
    from .device import DeviceRegistry
    from .driver import DriverRegistry
    from .process import ProcessTable
    from .thread import ThreadTable


class BootStage(Enum):
    """SIMULATOR: Kernel boot stages."""
    FIRMWARE_HANDOFF    = auto()  # BIOS/UEFI -> bootloader
    BOOTLOADER_HANDOFF  = auto()  # GRUB2 -> kernel entry
    ARCH_EARLY_INIT     = auto()  # GDT/IDT/TSS/paging/syscall MSR setup
    MEMORY_BRINGUP      = auto()  # PMM/VMM/kmalloc init
    INTERRUPT_TIMER_SETUP = auto() # IRQ/LAPIC timer setup
    SCHEDULER_START     = auto()  # scheduler + kernel threads
    VFS_DEVICE_INIT     = auto()  # rootfs mount + device/driver init
    USERSPACE_INIT      = auto()  # spawn init process (PID 1)


STAGE_EXPLANATIONS = {
    BootStage.FIRMWARE_HANDOFF: """\
FIRMWARE HANDOFF (BIOS/UEFI -> Bootloader):
  Real: Power-on triggers CPU reset vector at 0xFFFFFFF0 (16-bit real mode).
  BIOS performs POST (Power-On Self Test): memory test, hardware enumeration.
  UEFI: loads UEFI firmware drivers, reads ESP partition, finds bootloader.
  Hands control to MBR/bootloader with basic hardware initialized.
  SIMULATOR: We skip this stage - Python starts in 64-bit user-space already.""",

    BootStage.BOOTLOADER_HANDOFF: """\
BOOTLOADER HANDOFF (GRUB2/Multiboot2 -> Kernel):
  Real: GRUB2 loads kernel image (vmlinuz) and initramfs into physical memory.
  Passes Multiboot2 info block: memory map, command line, framebuffer info, ACPI RSDP.
  Switches CPU to 32-bit protected mode, jumps to kernel's 32-bit entry point.
  Kernel startup_32 switches to 64-bit long mode, jumps to startup_64.
  SIMULATOR: We simulate receiving the memory map and boot parameters.""",

    BootStage.ARCH_EARLY_INIT: """\
ARCH EARLY INIT (x86_64 architecture setup):
  Real: setup_arch() initializes:
  - GDT: Global Descriptor Table (kernel code/data, user code/data, TSS segments)
  - IDT: Interrupt Descriptor Table (256 vectors: exceptions 0-31, IRQs, syscalls)
  - TSS: Task State Segment (holds RSP0 = kernel stack pointer for ring-0 entry)
  - CR0/CR4: enable write-protect, PAE, PSE, SSE, SMEP, SMAP
  - Page tables: map kernel at 0xFFFF800000000000 (high half canonical)
  - IA32_LSTAR MSR: set SYSCALL entry point to entry_SYSCALL_64
  - CPUID: detect CPU features (NX, AVX, RDRAND, PCID, etc.)
  SIMULATOR: We call arch.detect_cpu_features(), setup_gdt(), setup_idt(), etc.""",

    BootStage.MEMORY_BRINGUP: """\
MEMORY BRINGUP (Physical and Virtual Memory Manager):
  Real: mm_init() initializes:
  - memblock: early boot allocator for pre-buddy allocations
  - Buddy allocator: organizes physical pages into power-of-2 free lists
  - Zone setup: DMA (<16MB), DMA32 (<4GB), NORMAL (rest)
  - mem_map: struct page array (one entry per physical page frame)
  - SLUB allocator: per-CPU slab caches for kmalloc()
  - vmalloc area: for large kernel allocations needing virtual contiguity
  SIMULATOR: We init PhysicalMemoryManager, VirtualMemoryManager, KmallocAllocator.""",

    BootStage.INTERRUPT_TIMER_SETUP: """\
INTERRUPT/TIMER SETUP (IRQ subsystem + LAPIC timer):
  Real: init_IRQ() sets up the interrupt controller:
  - Detect APIC (Advanced Programmable Interrupt Controller) via CPUID/ACPI
  - Initialize LAPIC (Local APIC) on each CPU: enable, set base address
  - Configure IOAPIC: route hardware IRQs to CPU LAPIC vectors
  - Calibrate the LAPIC timer against the HPET or TSC
  - Set up timer interrupt (IRQ0 or LAPIC timer) at HZ frequency (250Hz)
  - Initialize the softirq subsystem (NET_RX, NET_TX, TASKLET, SCHED, RCU)
  SIMULATOR: We simulate the timer concept without real APIC programming.""",

    BootStage.SCHEDULER_START: """\
SCHEDULER START (Kernel threads and run queue):
  Real: sched_init() creates per-CPU run queues. rest_init() spawns:
  - PID 1: kernel_init thread (will become /sbin/init)
  - PID 2: kthreadd (kernel thread daemon, spawns other kernel threads)
  Common kernel threads: kworker (workqueues), ksoftirqd (softirq), kswapd (swap).
  The idle task (PID 0 / swapper) runs HLT when run queue is empty.
  SIMULATOR: We call scheduler.init() and spawn kernel threads.""",

    BootStage.VFS_DEVICE_INIT: """\
VFS AND DEVICE INIT (Filesystem + device model):
  Real: vfs_caches_init() sets up dcache, icache. Initial rootfs is tmpfs (initramfs).
  The initramfs contains /init, /bin/sh, essential modules. After pivoting root,
  the real rootfs is mounted (ext4/btrfs from disk).
  Device model: device_register() for platform devices, PCI enumeration, driver probing.
  udev creates /dev nodes based on uevent notifications from the kernel.
  SIMULATOR: We mount tmpfs as /, create standard dirs, register simulated devices.""",

    BootStage.USERSPACE_INIT: """\
USERSPACE INIT (PID 1 / init):
  Real: kernel_init() mounts the real rootfs, runs /sbin/init (or systemd).
  init reads /etc/inittab or systemd unit files, starts services, gettys.
  The kernel's role is now to serve interrupts, syscalls, and scheduling.
  If /sbin/init fails, kernel_init() tries /etc/init, /bin/init, /bin/sh.
  SIMULATOR: We spawn the init process in the process table.""",
}


@dataclass
class BootStageResult:
    """SIMULATOR: Result of executing one boot stage."""
    stage:     BootStage
    success:   bool
    message:   str
    duration_ms: float = 0.0


class BootPipeline:
    """SIMULATOR: Models the kernel boot sequence from firmware to userspace.

    Each stage corresponds to a real boot phase. The pipeline can run all
    stages at once (run_all) or step through them one at a time (step).
    """

    def __init__(
        self,
        logger: "KernelLogger",
        arch: "ArchX86_64",
        memory: "Tuple[PhysicalMemoryManager, VirtualMemoryManager, KmallocAllocator]",
        scheduler: "Scheduler",
        vfs: "VFS",
        device_registry: "DeviceRegistry",
        driver_registry: "DriverRegistry",
        process_table: "ProcessTable",
        profile: "KernelProfile",
        thread_table: "ThreadTable",
    ):
        """SIMULATOR: Create a boot pipeline wired to all kernel subsystems."""
        self._log              = logger
        self._arch             = arch
        self._pmm, self._vmm, self._kmalloc = memory
        self._scheduler        = scheduler
        self._vfs              = vfs
        self._dev_reg          = device_registry
        self._drv_reg          = driver_registry
        self._proc_table       = process_table
        self._profile          = profile
        self._thread_table     = thread_table

        self._stages = list(BootStage)
        self._stage_index = 0
        self._results: List[BootStageResult] = []
        self._booted = False

    @property
    def is_booted(self) -> bool:
        """SIMULATOR: True if all boot stages completed successfully."""
        return self._booted

    @property
    def current_stage(self) -> Optional[BootStage]:
        """SIMULATOR: The next stage to be executed."""
        if self._stage_index < len(self._stages):
            return self._stages[self._stage_index]
        return None

    def explain_stage(self, stage: BootStage) -> str:
        """SIMULATOR: Return the educational explanation for a boot stage."""
        return STAGE_EXPLANATIONS.get(stage, f"No explanation for {stage.name}")

    def run_all(self) -> bool:
        """SIMULATOR: Run all boot stages in sequence. Returns True if all succeed."""
        self._log.info("BOOT", f"=== ComputeKERNEL-Edu Boot Sequence Starting (profile={self._profile.name}) ===")
        self._log.info("BOOT", "DISCLAIMER: This is a SIMULATED boot. No hardware is initialized.")

        while self._stage_index < len(self._stages):
            result = self._run_next()
            if not result.success:
                self._log.error("BOOT", f"Boot failed at stage {result.stage.name}: {result.message}")
                return False

        self._booted = True
        self._log.info("BOOT", "=== Boot sequence complete. System is running. ===")
        return True

    def step(self) -> Optional[BootStageResult]:
        """SIMULATOR: Execute the next boot stage. Returns None if already done."""
        if self._stage_index >= len(self._stages):
            return None
        return self._run_next()

    def _run_next(self) -> BootStageResult:
        """SIMULATOR: Execute the current stage and advance the index."""
        import time
        stage = self._stages[self._stage_index]
        self._stage_index += 1
        self._log.info("BOOT", f"--- Stage: {stage.name} ---")
        self._log.debug("BOOT", self.explain_stage(stage))
        t0 = time.monotonic()
        result = self._run_stage(stage)
        result.duration_ms = (time.monotonic() - t0) * 1000
        self._results.append(result)
        if result.success:
            self._log.info("BOOT", f"  [OK] {stage.name} ({result.duration_ms:.1f}ms)")
        else:
            self._log.error("BOOT", f"  [FAIL] {stage.name}: {result.message}")
        return result

    def _run_stage(self, stage: BootStage) -> BootStageResult:
        """SIMULATOR: Dispatch to the appropriate stage handler."""
        handlers = {
            BootStage.FIRMWARE_HANDOFF:     self._stage_firmware_handoff,
            BootStage.BOOTLOADER_HANDOFF:   self._stage_bootloader_handoff,
            BootStage.ARCH_EARLY_INIT:      self._stage_arch_early_init,
            BootStage.MEMORY_BRINGUP:       self._stage_memory_bringup,
            BootStage.INTERRUPT_TIMER_SETUP: self._stage_interrupt_timer_setup,
            BootStage.SCHEDULER_START:      self._stage_scheduler_start,
            BootStage.VFS_DEVICE_INIT:      self._stage_vfs_device_init,
            BootStage.USERSPACE_INIT:       self._stage_userspace_init,
        }
        handler = handlers.get(stage)
        if handler is None:
            return BootStageResult(stage, False, f"No handler for {stage.name}")
        try:
            return handler()
        except Exception as e:
            return BootStageResult(stage, False, str(e))

    # -------------------------------------------------------------------------
    # Stage implementations
    # -------------------------------------------------------------------------

    def _stage_firmware_handoff(self) -> BootStageResult:
        """SIMULATOR: Model BIOS/UEFI firmware initialization."""
        self._log.info("BOOT", "[FIRMWARE] BIOS/UEFI POST complete (simulated)")
        self._log.info("BOOT", "[FIRMWARE] Memory map provided by firmware:")
        self._log.info("BOOT", "[FIRMWARE]   0x00000000-0x0009FFFF  640KB  usable")
        self._log.info("BOOT", "[FIRMWARE]   0x000A0000-0x000FFFFF  384KB  reserved (VGA/ROM)")
        self._log.info("BOOT", "[FIRMWARE]   0x00100000-0x3FFFFFFF  1GB-1MB usable")
        self._log.info("BOOT", "[FIRMWARE]   0x40000000-0x400FFFFF  1MB    ACPI NVS")
        self._log.info("BOOT", "[FIRMWARE] ACPI tables detected at 0x7FFDF000")
        self._log.info("BOOT", "[FIRMWARE] Real: UEFI handoff passes control to bootloader via ESP")
        return BootStageResult(BootStage.FIRMWARE_HANDOFF, True,
                               "Firmware handoff simulated (no real hardware)")

    def _stage_bootloader_handoff(self) -> BootStageResult:
        """SIMULATOR: Model GRUB2/Multiboot2 -> kernel handoff."""
        self._log.info("BOOT", "[BOOTLDR] GRUB2 loading kernel image... (simulated)")
        self._log.info("BOOT", "[BOOTLDR] kernel: computekernel-edu (Python simulator)")
        self._log.info("BOOT", "[BOOTLDR] cmdline: profile=" + self._profile.name)
        self._log.info("BOOT", "[BOOTLDR] Multiboot2 info block passed to kernel entry")
        self._log.info("BOOT", "[BOOTLDR] Memory map: 1024 pages (4 MB simulated RAM)")
        self._log.info("BOOT", "[BOOTLDR] Real: GRUB2 maps kernel ELF segments, passes phys addr of Multiboot2 struct in rbx")
        self._log.info("BOOT", "[BOOTLDR] Real: startup_32 -> enable_paging -> startup_64 -> start_kernel()")
        return BootStageResult(BootStage.BOOTLOADER_HANDOFF, True,
                               "Bootloader handoff simulated")

    def _stage_arch_early_init(self) -> BootStageResult:
        """SIMULATOR: Model x86_64 architecture initialization."""
        self._log.info("BOOT", "[ARCH] Detecting CPU features via CPUID (simulated)...")
        features = self._arch.detect_cpu_features()
        self._log.info("BOOT", f"[ARCH] CPU: cores={features.cores} threads_per_core={features.threads_per_core}")
        self._log.info("BOOT", f"[ARCH] Features: NX={features.has_nx} SSE2={features.has_sse2} "
                       f"AVX2={features.has_avx2} RDRAND={features.has_rdrand}")
        self._log.info("BOOT", f"[ARCH] SMEP={features.has_smep} SMAP={features.has_smap} PCID={features.has_pcid}")

        self._log.info("BOOT", "[ARCH] Setting up GDT (Global Descriptor Table)...")
        gdt = self._arch.setup_gdt()
        for entry in gdt:
            self._log.debug("BOOT", f"[ARCH]   GDT: {entry.description} base={entry.base:#x} limit={entry.limit:#x}")

        self._log.info("BOOT", "[ARCH] Setting up TSS (Task State Segment)...")
        tss = self._arch.setup_tss()
        self._log.debug("BOOT", f"[ARCH]   TSS: RSP0=0x{tss.rsp0:016x} (kernel stack for ring-0 entry)")

        self._log.info("BOOT", "[ARCH] Setting up IDT (256 interrupt vectors)...")
        idt = self._arch.setup_idt()
        self._log.info("BOOT", f"[ARCH]   IDT: {len(idt)} vectors configured")

        self._log.info("BOOT", "[ARCH] Setting up 4-level page tables (PML4->PDPT->PD->PT)...")
        paging_info = self._arch.setup_paging()
        self._log.info("BOOT", f"[ARCH]   {paging_info}")

        self._log.info("BOOT", "[ARCH] Configuring SYSCALL entry (IA32_LSTAR MSR)...")
        syscall_info = self._arch.setup_syscall_entry()
        self._log.info("BOOT", f"[ARCH]   {syscall_info}")

        self._log.info("BOOT", "[ARCH] Real: LGDT/LIDT instructions load descriptor tables")
        self._log.info("BOOT", "[ARCH] Real: CR0.WP=1, CR4.PAE=1, CR4.SMEP=1, CR4.SMAP=1")
        self._log.info("BOOT", "[ARCH] Real: WRMSR(IA32_LSTAR, &entry_SYSCALL_64)")
        return BootStageResult(BootStage.ARCH_EARLY_INIT, True,
                               f"Arch init: {features.cores} cores, {len(gdt)} GDT entries, {len(idt)} IDT vectors")

    def _stage_memory_bringup(self) -> BootStageResult:
        """SIMULATOR: Model PMM/VMM/kmalloc initialization."""
        self._log.info("BOOT", f"[MM] Physical memory: {self._pmm.total_pages} pages "
                       f"({self._pmm.total_pages * 4096 // 1024} KB simulated)")
        self._log.info("BOOT", f"[MM] Free pages: {self._pmm.free_pages}")
        self._log.info("BOOT", "[MM] Real: buddy allocator initialized per memory zone")
        self._log.info("BOOT", "[MM] Real: SLUB allocator: per-CPU slab caches for kmalloc-8 to kmalloc-8M")
        self._log.info("BOOT", "[MM] Real: vmalloc_init() sets up vmalloc address space (VMALLOC_START..END)")

        # Create kernel virtual address space (pid=0)
        self._vmm.create_address_space(0)
        self._log.info("BOOT", "[MM] Kernel address space created (pid=0)")

        # Simulate a few early kernel allocations
        addr1 = self._kmalloc.alloc(512)
        addr2 = self._kmalloc.alloc(256)
        self._log.debug("BOOT", f"[MM] kmalloc test: 512B -> 0x{addr1:016x}, 256B -> 0x{addr2:016x}")
        self._kmalloc.free(addr1)
        self._kmalloc.free(addr2)
        self._log.debug("BOOT", "[MM] kmalloc test: freed both allocations")

        stats = self._pmm.stats()
        return BootStageResult(BootStage.MEMORY_BRINGUP, True,
                               f"PMM: {stats['total_pages']} pages, {stats['free_pages']} free")

    def _stage_interrupt_timer_setup(self) -> BootStageResult:
        """SIMULATOR: Model IRQ/LAPIC timer setup."""
        self._log.info("BOOT", "[IRQ] Initializing interrupt subsystem (simulated)...")
        self._log.info("BOOT", "[IRQ] Real: Detect APIC via CPUID.01H:EDX bit 9")
        self._log.info("BOOT", "[IRQ] Real: enable_local_apic() -> map LAPIC at 0xFEE00000")
        self._log.info("BOOT", "[IRQ] Real: Calibrate LAPIC timer against HPET/TSC")
        self._log.info("BOOT", "[IRQ] Real: HPET at 0xFED00000 for high-precision timing")
        self._log.info("BOOT", f"[IRQ] Simulated timer frequency: {1000 // (1000 // 250)} Hz "
                       f"(CONFIG_HZ=250 equivalent)")
        self._log.info("BOOT", "[IRQ] Softirq vectors initialized: TIMER, NET_TX, NET_RX, TASKLET, SCHED, RCU")
        self._log.info("BOOT", "[IRQ] RCU (Read-Copy-Update) subsystem initialized")
        self._log.info("BOOT", "[IRQ] Real: request_irq(0, timer_interrupt, ...) for PIT/HPET")
        self._log.info("BOOT", "[IRQ] SIMULATOR: No real IRQs will fire - ticks are manual")
        return BootStageResult(BootStage.INTERRUPT_TIMER_SETUP, True,
                               "Timer/IRQ subsystem simulated (no real APIC)")

    def _stage_scheduler_start(self) -> BootStageResult:
        """SIMULATOR: Model scheduler initialization and kernel thread spawning."""
        self._log.info("BOOT", "[SCHED] Initializing scheduler...")
        self._scheduler.init(self._thread_table)

        # Spawn core kernel threads (analogous to Linux's kernel threads)
        kworker = self._thread_table.spawn(pid=0, name="kworker/0:0",
                                            is_kernel_thread=True)
        ksoftirqd = self._thread_table.spawn(pid=0, name="ksoftirqd/0",
                                              is_kernel_thread=True)
        kswapd = self._thread_table.spawn(pid=0, name="kswapd0",
                                           is_kernel_thread=True)

        self._scheduler.add_thread(kworker)
        self._scheduler.add_thread(ksoftirqd)
        self._scheduler.add_thread(kswapd)

        self._log.info("BOOT", f"[SCHED] Kernel threads spawned: "
                       f"kworker tid={kworker.tid}, "
                       f"ksoftirqd tid={ksoftirqd.tid}, "
                       f"kswapd tid={kswapd.tid}")
        self._log.info("BOOT", "[SCHED] Run queue has "
                       f"{len(self._scheduler.runqueue)} threads")
        self._log.info("BOOT", "[SCHED] Real: kworker handles deferred work (workqueues)")
        self._log.info("BOOT", "[SCHED] Real: ksoftirqd handles softirq overflow")
        self._log.info("BOOT", "[SCHED] Real: kswapd reclaims memory under memory pressure")

        # Simulate a few ticks to show the scheduler is running
        self._scheduler.tick_n(5)
        sched_status = self._scheduler.status()
        self._log.debug("BOOT", f"[SCHED] After 5 ticks: {sched_status['context_switches']} context switches")

        return BootStageResult(BootStage.SCHEDULER_START, True,
                               f"Scheduler running, {len(self._scheduler.runqueue)} threads in runqueue")

    def _stage_vfs_device_init(self) -> BootStageResult:
        """SIMULATOR: Model VFS mount and device/driver initialization."""
        from .fs_tmpfs import TmpFS
        from .device import Device, DeviceClass
        from .driver import Driver

        # Mount tmpfs as root filesystem
        self._log.info("BOOT", "[VFS] Mounting tmpfs as root filesystem /")
        rootfs = TmpFS(self._log)
        self._vfs.mount("/", rootfs, "tmpfs")

        # Create standard directory structure
        for d in ["dev", "proc", "sys", "tmp", "etc", "bin", "usr", "var", "home"]:
            self._vfs.mkdir(f"/{d}")
            self._log.debug("BOOT", f"[VFS] mkdir /{d}")

        # Create /etc/version
        self._vfs.create_file("/etc/version",
                               b"ComputeKERNEL-Edu v0.1.0 (educational simulator)\n")
        self._vfs.create_file("/etc/hostname", b"computekernel-edu\n")

        self._log.info("BOOT", "[VFS] Real: initramfs is unpacked into tmpfs rootfs")
        self._log.info("BOOT", "[VFS] Real: pivot_root() or switch_root() transitions to real rootfs")
        self._log.info("BOOT", "[VFS] Real: /proc (procfs), /sys (sysfs) are mounted")

        # Register simulated devices
        devices = [
            Device("console",   DeviceClass.CHAR,    major=5,  minor=1,  description="System console"),
            Device("tty0",      DeviceClass.CHAR,    major=4,  minor=0,  description="Virtual terminal 0"),
            Device("null",      DeviceClass.CHAR,    major=1,  minor=3,  description="Null device"),
            Device("zero",      DeviceClass.CHAR,    major=1,  minor=5,  description="Zero device"),
            Device("random",    DeviceClass.CHAR,    major=1,  minor=8,  description="Random device"),
            Device("timer0",    DeviceClass.TIMER,   major=0,  minor=0,  description="System timer"),
            Device("sda",       DeviceClass.BLOCK,   major=8,  minor=0,  description="Simulated SATA disk"),
            Device("keyboard0", DeviceClass.INPUT,   major=13, minor=0,  description="PS/2 keyboard"),
        ]
        for dev in devices:
            self._dev_reg.register(dev)

        self._log.info("BOOT", f"[DEV] {len(devices)} devices registered")

        # Register drivers
        console_driver = Driver(
            name="uart16550",
            description="16550A UART serial driver",
            supported_devices=["console", "tty0"],
        )
        null_driver = Driver(
            name="mem_dev",
            description="Memory character devices (null, zero, random)",
            supported_devices=["null", "zero", "random"],
        )
        disk_driver = Driver(
            name="ahci",
            description="AHCI SATA controller driver",
            supported_devices=["sda"],
        )
        kbd_driver = Driver(
            name="ps2kbd",
            description="PS/2 keyboard driver",
            supported_devices=["keyboard0"],
        )
        for drv in [console_driver, null_driver, disk_driver, kbd_driver]:
            self._drv_reg.register(drv)

        # Probe all devices
        self._drv_reg.probe_all(self._dev_reg)
        self._log.info("BOOT", "[DEV] Driver probing complete")
        self._log.info("BOOT", "[DEV] Real: PCI bus enumeration reads config space")
        self._log.info("BOOT", "[DEV] Real: ACPI namespace walk for ACPI devices")

        return BootStageResult(BootStage.VFS_DEVICE_INIT, True,
                               f"tmpfs mounted, {len(devices)} devices, drivers bound")

    def _stage_userspace_init(self) -> BootStageResult:
        """SIMULATOR: Model spawning the init process (PID 1)."""
        from .process import TaskState

        self._log.info("BOOT", "[INIT] Spawning init process (PID 1)...")

        # In a real kernel, PID 1 is spawned by kernel_init() thread
        # We simulate it here
        init_proc = self._proc_table.spawn(
            name="init",
            ppid=0,
            uid=0,
            gid=0,
            cmdline="/sbin/init",
        )
        init_proc.state = TaskState.RUNNABLE
        init_proc.cwd = "/"

        # Create init thread
        init_thread = self._thread_table.spawn(
            pid=init_proc.pid,
            name="init",
            is_kernel_thread=False,
        )
        self._scheduler.add_thread(init_thread)

        # Create address space for init
        self._vmm.create_address_space(init_proc.pid)

        self._log.info("BOOT", f"[INIT] init process: pid={init_proc.pid} tid={init_thread.tid}")
        self._log.info("BOOT", "[INIT] Real: kernel_init() -> run_init_process('/sbin/init')")
        self._log.info("BOOT", "[INIT] Real: execve('/sbin/init', ...) -> ELF loaded into pid 1")
        self._log.info("BOOT", "[INIT] Real: systemd (or SysV init) reads unit files, starts services")
        self._log.info("BOOT", "[INIT] SIMULATOR: init process is in runqueue, ready to be scheduled")
        self._log.info("BOOT", "")
        self._log.info("BOOT", "  ComputeKERNEL-Edu is running. Type 'help' for commands.")
        self._log.info("BOOT", "")

        sched_status = self._scheduler.status()
        return BootStageResult(
            BootStage.USERSPACE_INIT,
            True,
            f"init spawned as pid={init_proc.pid}, "
            f"runqueue={sched_status['runqueue_length']} threads"
        )

    def get_log(self) -> List[BootStageResult]:
        """SIMULATOR: Return the list of all boot stage results."""
        return list(self._results)
