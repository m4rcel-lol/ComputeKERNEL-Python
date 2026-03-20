"""
SIMULATOR: Kernel module loader.
Models the Linux loadable kernel module (LKM) subsystem.

Real kernel: Modules (.ko files) are ELF shared objects. insmod/modprobe calls
finit_module()/init_module() syscalls. The kernel loads the ELF, resolves symbols
against the kernel symbol table (kallsyms), runs relocation, and calls the module's
init() function. rmmod calls the module's exit() function then frees the pages.

SIMULATOR: We track module metadata in Python dataclasses without any ELF loading.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from .logger import KernelLogger
from .profiles import KernelProfile


@dataclass
class KernelModule:
    """SIMULATOR: Represents a loadable kernel module (struct module analog).

    Real kernel: struct module contains name, state (COMING/LIVE/GOING),
    init/exit function pointers, exported symbol table, parameter table,
    reference count, and the module's ELF sections (text, data, bss).
    """
    name:         str
    version:      str
    description:  str
    dependencies: List[str]      # modules that must be loaded first
    exports:      List[str]      # symbols this module exports
    is_loaded:    bool           = False
    parameters:   Dict[str, str] = field(default_factory=dict)


class ModuleLoader:
    """SIMULATOR: Kernel module loader (insmod/rmmod/lsmod analog).

    Real kernel: The module loader (kernel/module.c) handles the full
    lifecycle: loading the .ko ELF, resolving symbols, calling init(),
    managing the module reference count, and calling exit() on rmmod.
    """

    def __init__(self, logger: KernelLogger, profile: KernelProfile):
        """SIMULATOR: Create a module loader respecting the given profile."""
        self._logger = logger
        self._profile = profile
        self._available: Dict[str, KernelModule] = {}
        self._symbol_table: Dict[str, str] = {}  # symbol_name -> module_name

    def register(self, module: KernelModule):
        """SIMULATOR: Register a module as available (add to available pool)."""
        self._available[module.name] = module

    def load(self, name: str) -> bool:
        """SIMULATOR: Load a kernel module (insmod analog).

        Real kernel: finit_module() syscall -> load_module() -> resolve_symbol_wait()
        -> simplify_symbols() -> apply_relocations() -> module->init().
        """
        if not self._profile.modules_enabled:
            self._logger.warn("MOD", f"insmod '{name}': modules disabled in profile '{self._profile.name}'")
            return False

        mod = self._available.get(name)
        if mod is None:
            self._logger.error("MOD", f"insmod '{name}': module not found")
            return False

        if mod.is_loaded:
            self._logger.info("MOD", f"insmod '{name}': already loaded")
            return True

        # Check dependencies
        for dep in mod.dependencies:
            dep_mod = self._available.get(dep)
            if dep_mod is None or not dep_mod.is_loaded:
                self._logger.error("MOD", f"insmod '{name}': unresolved dependency '{dep}'")
                return False

        # Mark loaded and register symbols
        mod.is_loaded = True
        for sym in mod.exports:
            self._symbol_table[sym] = name

        self._logger.info("MOD", (
            f"insmod: loaded '{name}' v{mod.version} "
            f"exports={len(mod.exports)} deps={mod.dependencies}"
        ))
        return True

    def unload(self, name: str) -> bool:
        """SIMULATOR: Unload a kernel module (rmmod analog).

        Real kernel: delete_module() syscall -> free_module() -> module->exit(),
        waits for reference count to drop to zero.
        """
        mod = self._available.get(name)
        if mod is None:
            self._logger.error("MOD", f"rmmod '{name}': module not found")
            return False

        if not mod.is_loaded:
            self._logger.warn("MOD", f"rmmod '{name}': not loaded")
            return False

        # Check if any other loaded module depends on this one
        for other in self._available.values():
            if other.is_loaded and name in other.dependencies:
                self._logger.error("MOD", f"rmmod '{name}': still needed by '{other.name}'")
                return False

        # Remove symbols
        for sym in mod.exports:
            self._symbol_table.pop(sym, None)

        mod.is_loaded = False
        self._logger.info("MOD", f"rmmod: unloaded '{name}'")
        return True

    def list_loaded(self) -> List[KernelModule]:
        """SIMULATOR: Return all currently loaded modules (lsmod analog)."""
        return [m for m in self._available.values() if m.is_loaded]

    def list_available(self) -> List[KernelModule]:
        """SIMULATOR: Return all available (registered) modules."""
        return list(self._available.values())

    def lookup_symbol(self, symbol: str) -> Optional[str]:
        """SIMULATOR: Look up which module provides a symbol (kallsyms analog)."""
        return self._symbol_table.get(symbol)

    def symbol_table(self) -> Dict[str, str]:
        """SIMULATOR: Return the full exported symbol table."""
        return dict(self._symbol_table)


def make_default_modules() -> List[KernelModule]:
    """SIMULATOR: Create the default set of available kernel modules."""
    return [
        KernelModule(
            "ext2", "1.0", "Ext2 filesystem driver",
            [], ["ext2_fill_super", "ext2_write_inode"], False,
        ),
        KernelModule(
            "tmpfs", "1.0", "Tmpfs in-memory filesystem",
            [], ["tmpfs_fill_super"], False,
        ),
        KernelModule(
            "ata", "1.0", "ATA/ATAPI disk driver",
            [], ["ata_probe", "ata_read"], False,
        ),
        KernelModule(
            "virtio_blk", "1.0", "VirtIO block device driver",
            [], ["virtio_blk_probe"], False,
        ),
        KernelModule(
            "keyboard", "1.0", "PS/2 keyboard driver",
            [], ["kbd_irq_handler"], False,
        ),
        KernelModule(
            "serial", "1.0", "16550 UART serial driver",
            [], ["serial_init", "serial_write"], False,
        ),
    ]
