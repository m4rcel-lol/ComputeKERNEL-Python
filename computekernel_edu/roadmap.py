"""
SIMULATOR: ComputeKERNEL feature roadmap.
Shows what is implemented in this educational simulator vs what is planned.
"""

IMPLEMENTED = [
    ("Boot pipeline simulation",           "boot.py",        "Full"),
    ("x86_64 arch layer model",            "arch.py",        "Full"),
    ("Physical memory manager (PMM)",      "memory.py",      "Full"),
    ("Virtual memory manager (VMM)",       "memory.py",      "Full"),
    ("kmalloc/slab allocator model",       "memory.py",      "Full"),
    ("Process model (task_struct)",        "process.py",     "Full"),
    ("Thread model (CPU context)",         "thread.py",      "Full"),
    ("Round-robin preemptive scheduler",   "scheduler.py",   "Full"),
    ("Syscall table (14 syscalls)",        "syscall.py",     "Full"),
    ("VFS (Virtual Filesystem Switch)",    "vfs.py",         "Full"),
    ("tmpfs (in-memory FS)",               "fs_tmpfs.py",    "Full"),
    ("Ext2-inspired FS model",             "fs_ext2.py",     "Educational"),
    ("Device registry",                    "device.py",      "Full"),
    ("Driver framework",                   "driver.py",      "Full"),
    ("Serial console / TTY",               "console.py",     "Full"),
    ("ELF loader model",                   "elfloader.py",   "Educational"),
    ("Pipes and signals (IPC)",            "ipc.py",         "Full"),
    ("Kernel module loader",               "module_loader.py", "Full"),
    ("Security / credentials",             "security.py",    "Full"),
    ("Power management states",            "power.py",       "Full"),
    ("Boot profiles (debug/release/safe)", "profiles.py",    "Full"),
    ("Safe mode enforcement",              "safe_mode.py",   "Full"),
    ("Teaching engine",                    "teaching.py",    "Full"),
    ("Interactive shell",                  "shell.py",       "Full"),
]

ROADMAP = [
    ("TCP/IP network stack",       "In-kernel TCP/IP (lwIP or custom)", "Planned"),
    ("Network device driver model","NIC driver framework",             "Planned"),
    ("SSH daemon",                 "In-kernel SSH service",            "Planned"),
    ("SMP (multi-core) support",   "Per-CPU scheduler, IPI, spinlocks","Planned"),
    ("ACPI power management",      "Full ACPI AML interpreter",        "Planned"),
    ("USB stack",                  "xHCI host controller + USB drivers","Planned"),
    ("NVMe driver",                "PCIe NVMe block device driver",    "Planned"),
    ("ext4 filesystem",            "Full ext4 with journaling",        "Planned"),
    ("procfs / sysfs",             "Runtime kernel info filesystems",  "Planned"),
    ("Memory-mapped files",        "mmap(MAP_FILE) with page cache",   "Planned"),
    ("Copy-on-write fork",         "Real COW fork() implementation",   "Planned"),
    ("POSIX threads (pthreads)",   "Full pthread support",             "Planned"),
    ("ASLR",                       "Address space layout randomization","Planned"),
    ("KVM hypervisor support",     "Paravirtualization",               "Planned"),
    ("DRM/KMS graphics",           "Framebuffer + GPU driver model",   "Planned"),
    ("Audio subsystem",            "ALSA-style audio model",           "Planned"),
    ("Bluetooth stack",            "HCI/L2CAP model",                  "Planned"),
    ("SELinux/AppArmor model",     "Mandatory access control",         "Planned"),
    ("eBPF subsystem",             "In-kernel safe programs",          "Planned"),
    ("io_uring",                   "Async I/O interface",              "Planned"),
]

NOTE_ON_NETWORKING = """
NOTE: Networking is on the ComputeKERNEL roadmap.
The current implementation (both real C kernel and this Python simulator)
does NOT include a TCP/IP stack, network device drivers, or an SSH daemon.
These are planned features. The 'netinfo' command shows this status.
"""


def format_roadmap() -> str:
    """SIMULATOR: Format the full roadmap as a readable string."""
    lines = ["=" * 70, "ComputeKERNEL-Edu: Feature Roadmap", "=" * 70, ""]
    lines.append("IMPLEMENTED (in this simulator):")
    lines.append("-" * 50)
    for name, module, status in IMPLEMENTED:
        mark = "X" if status in ("Full", "Educational") else " "
        lines.append(f"  [{mark}] {name:<44} ({module})")
    lines.append("")
    lines.append("PLANNED / ROADMAP (not yet implemented):")
    lines.append("-" * 50)
    for name, detail, status in ROADMAP:
        lines.append(f"  [ ] {name:<44} - {detail}")
    lines.append("")
    lines.append(NOTE_ON_NETWORKING.strip())
    return "\n".join(lines)
