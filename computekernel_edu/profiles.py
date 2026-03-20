"""
SIMULATOR: Boot profiles for ComputeKERNEL-Edu.
Models the kernel build/boot configuration profiles (debug, release, safe_mode).

Real kernel: Equivalent to kernel config options (CONFIG_DEBUG_*, CONFIG_SLUB_DEBUG, etc.)
and kernel command-line parameters (init=, nomodules, etc.).
"""

from dataclasses import dataclass


@dataclass
class KernelProfile:
    """SIMULATOR: A kernel boot/build profile.

    Controls which features are enabled, logging verbosity, and restrictions.
    Analogous to a combination of kernel Kconfig options and kernel cmdline flags.
    """
    name:                  str
    description:           str
    serial_log:            bool   # print log entries to stdout (serial console sink)
    debug_symbols:         bool   # include extra debug metadata
    modules_enabled:       bool   # allow kernel module loading
    non_essential_drivers: bool   # load non-essential device drivers
    kmalloc_debug:         bool   # enable kmalloc poisoning / redzone checks
    scheduler_debug:       bool   # extra scheduler logging
    mm_debug:              bool   # extra memory manager logging
    max_log_level:         int    # minimum level to print (0=DEBUG, 1=INFO, ...)
    panic_on_oops:         bool   # panic on first kernel oops
    nx_enforcement:        bool   # enforce NX (no-execute) page bits
    aslr:                  bool   # address space layout randomization
    smep:                  bool   # Supervisor Mode Execution Prevention
    smap:                  bool   # Supervisor Mode Access Prevention


DEBUG_PROFILE = KernelProfile(
    name="debug",
    description="Full debug build: verbose logging, all drivers, all modules, extra checks.",
    serial_log=True,
    debug_symbols=True,
    modules_enabled=True,
    non_essential_drivers=True,
    kmalloc_debug=True,
    scheduler_debug=True,
    mm_debug=True,
    max_log_level=0,         # DEBUG and above
    panic_on_oops=False,
    nx_enforcement=True,
    aslr=False,              # disabled for deterministic debugging
    smep=True,
    smap=True,
)

RELEASE_PROFILE = KernelProfile(
    name="release",
    description="Release build: minimal logging, optimized, ASLR enabled.",
    serial_log=False,
    debug_symbols=False,
    modules_enabled=True,
    non_essential_drivers=True,
    kmalloc_debug=False,
    scheduler_debug=False,
    mm_debug=False,
    max_log_level=1,         # INFO and above
    panic_on_oops=True,
    nx_enforcement=True,
    aslr=True,
    smep=True,
    smap=True,
)

SAFE_MODE_PROFILE = KernelProfile(
    name="safe_mode",
    description="Safe/recovery mode: minimal drivers, no modules, verbose logging.",
    serial_log=True,
    debug_symbols=True,
    modules_enabled=False,
    non_essential_drivers=False,
    kmalloc_debug=True,
    scheduler_debug=False,
    mm_debug=False,
    max_log_level=0,
    panic_on_oops=False,
    nx_enforcement=True,
    aslr=False,
    smep=True,
    smap=False,              # disabled in safe mode for easier recovery
)

PROFILES: dict[str, KernelProfile] = {
    "debug":     DEBUG_PROFILE,
    "release":   RELEASE_PROFILE,
    "safe_mode": SAFE_MODE_PROFILE,
}
