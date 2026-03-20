"""
SIMULATOR: ELF executable loader - educational model only.
NOT real ELF binary parsing. Models the concept of loading an ELF executable
into a process address space.

Real kernel: The ELF loader (fs/binfmt_elf.c in Linux) reads the ELF header,
validates the magic (0x7f 'E' 'L' 'F'), checks architecture, maps PT_LOAD
segments into the process address space (text at given vaddr r-x, data rw-,
bss zeroed), sets up stack, dynamic linker (PT_INTERP), and jumps to e_entry.

SIMULATOR: We model the data structures and "loading" process conceptually.
"""

from dataclasses import dataclass, field
from typing import List, Optional
from .memory import VirtualMemoryManager, PAGE_SIZE
from .logger import KernelLogger

ELF_MAGIC = b'\x7fELF'


@dataclass
class ElfSegment:
    """SIMULATOR: Models an ELF PT_LOAD program header segment."""
    seg_type:  str   # "PT_LOAD", "PT_DYNAMIC", "PT_INTERP"
    vaddr:     int   # virtual address to load at
    size:      int   # size in memory
    file_size: int   # size in file (rest is BSS / zero-fill)
    flags:     str   # "r-x" (text), "rw-" (data/bss)
    name:      str   # human label: "text", "data", "bss"


@dataclass
class FakeElf:
    """SIMULATOR: A fake ELF binary representation for educational loading.

    In reality an ELF binary starts with a 64-byte ELF header (Ehdr),
    followed by program headers (Phdr) and section headers (Shdr).
    Here we just have Python fields.
    """
    name:        str
    entry_point: int = 0x400000
    segments:    List[ElfSegment] = field(default_factory=list)
    interpreter: str = "/lib64/ld-linux-x86-64.so.2"
    arch:        str = "x86_64"

    @staticmethod
    def make_simple(name: str, base: int = 0x400000) -> "FakeElf":
        """SIMULATOR: Create a simple fake ELF with text, data, bss segments."""
        return FakeElf(
            name=name,
            entry_point=base,
            segments=[
                ElfSegment("PT_LOAD", base,           0x1000, 0x1000, "r-x", "text"),
                ElfSegment("PT_LOAD", base + 0x200000, 0x1000, 0x800,  "rw-", "data"),
                ElfSegment("PT_LOAD", base + 0x201000, 0x1000, 0,      "rw-", "bss"),
            ],
        )


class ElfLoader:
    """SIMULATOR: Educational ELF loader.

    Models the process of loading an ELF into a virtual address space,
    creating VMAs for each PT_LOAD segment.
    """

    def __init__(self, vmm: VirtualMemoryManager, logger: KernelLogger):
        """SIMULATOR: Create an ELF loader using the given VMM."""
        self._vmm = vmm
        self._logger = logger

    def load(self, elf: FakeElf, pid: int) -> int:
        """SIMULATOR: Load a FakeElf into pid's address space. Returns entry point.

        Real kernel analog: load_elf_binary() in fs/binfmt_elf.c:
        1. Parse ELF header, validate magic/arch/type
        2. For each PT_LOAD segment: mmap into address space at p_vaddr
        3. Copy p_filesz bytes, zero-fill p_memsz - p_filesz (BSS)
        4. Set up stack, aux vector, dynamic linker if PT_INTERP present
        5. Return e_entry as the initial RIP for execve()
        """
        self._logger.info("KERN", f"ELF load: '{elf.name}' pid={pid} entry=0x{elf.entry_point:016x}")

        as_ = self._vmm.address_spaces.get(pid)
        if as_ is None:
            self._logger.error("KERN", f"ELF load: no address space for pid={pid}")
            return -1

        for seg in elf.segments:
            self._vmm.map_pages(pid, seg.vaddr, seg.size, seg.flags, f"[{seg.name}]")
            self._logger.debug(
                "KERN",
                f"  map segment: {seg.name} vaddr=0x{seg.vaddr:016x} "
                f"size={seg.size} flags={seg.flags}"
            )
            if seg.name == "bss":
                self._logger.debug("KERN", f"  zero-filling BSS: {seg.size} bytes")

        # Set up stack (if not already present)
        stack_vaddr = 0x00007fff00000000
        self._vmm.map_pages(pid, stack_vaddr, 0x100000, "rw-", "[stack]")
        self._logger.debug("KERN", f"  stack mapped at 0x{stack_vaddr:016x}")

        self._logger.info("KERN", f"ELF load complete: entry=0x{elf.entry_point:016x}")
        return elf.entry_point
