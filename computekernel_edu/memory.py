"""
SIMULATOR: Memory management subsystem.
Models physical memory manager (PMM), virtual memory manager (VMM),
page table concepts, and kernel allocator (kmalloc/slab).

Real kernel: PMM manages physical page frames via a buddy allocator.
VMM manages virtual address spaces via page tables (PML4/PDPT/PD/PT on x86_64).
Slab/SLUB allocator handles small kernel allocations.

SIMULATOR: We use Python dicts/lists to model these concepts without
actual page table manipulation or physical memory.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from .logger import KernelLogger

PAGE_SIZE = 4096
KERNEL_BASE = 0xFFFF800000000000  # x86_64 high-half kernel base
USER_MAX    = 0x00007FFFFFFFFFFF  # x86_64 user address space ceiling

DEFAULT_PHYS_PAGES = 1024  # 4 MB of simulated physical memory


@dataclass
class Page:
    """SIMULATOR: Represents a physical page frame."""
    pfn: int       # page frame number
    in_use: bool = False
    owner_pid: int = 0

    @property
    def phys_addr(self) -> int:
        """SIMULATOR: Physical address of this page frame."""
        return self.pfn * PAGE_SIZE


class PhysicalMemoryManager:
    """SIMULATOR: Models the physical memory manager (buddy allocator concept).

    In a real kernel the PMM ingests the memory map from firmware/bootloader
    and manages page frames with a buddy allocator for efficient splitting/merging.
    Here we use a flat list of Page objects.
    """

    def __init__(self, total_pages: int, logger: KernelLogger):
        """SIMULATOR: Initialize PMM with a fixed number of simulated page frames."""
        self.total_pages = total_pages
        self._pages: List[Page] = [Page(pfn=i) for i in range(total_pages)]
        self._logger = logger

    @property
    def free_pages(self) -> int:
        """SIMULATOR: Count of currently free page frames."""
        return sum(1 for p in self._pages if not p.in_use)

    @property
    def used_pages(self) -> int:
        """SIMULATOR: Count of currently allocated page frames."""
        return sum(1 for p in self._pages if p.in_use)

    def alloc_page(self, pid: int = 0) -> Optional[Page]:
        """SIMULATOR: Allocate one physical page frame."""
        for page in self._pages:
            if not page.in_use:
                page.in_use = True
                page.owner_pid = pid
                self._logger.debug("MM", f"alloc_page: pfn={page.pfn} pid={pid} phys=0x{page.phys_addr:016x}")
                return page
        self._logger.error("MM", "alloc_page: OUT OF MEMORY")
        return None

    def free_page(self, pfn: int):
        """SIMULATOR: Free a physical page frame."""
        if 0 <= pfn < self.total_pages:
            self._pages[pfn].in_use = False
            self._pages[pfn].owner_pid = 0
            self._logger.debug("MM", f"free_page: pfn={pfn}")
        else:
            self._logger.error("MM", f"free_page: invalid pfn={pfn}")

    def alloc_pages(self, n: int, pid: int = 0) -> List[Page]:
        """SIMULATOR: Allocate n pages (simplified, not truly contiguous)."""
        result = []
        for _ in range(n):
            p = self.alloc_page(pid)
            if p is None:
                # OOM: free what we allocated and return empty
                for already in result:
                    self.free_page(already.pfn)
                return []
            result.append(p)
        return result

    def stats(self) -> dict:
        """SIMULATOR: Return memory usage statistics."""
        return {
            "total_pages": self.total_pages,
            "free_pages": self.free_pages,
            "used_pages": self.used_pages,
            "total_bytes": self.total_pages * PAGE_SIZE,
            "free_bytes": self.free_pages * PAGE_SIZE,
        }


@dataclass
class VirtualMemoryArea:
    """SIMULATOR: Models a VMA (virtual memory area / vm_area_struct).

    In a real kernel, each VMA is a contiguous region of a process's virtual
    address space with uniform permissions (read/write/exec) and a backing.
    """
    start: int
    end: int
    flags: str   # e.g. "r--", "rw-", "r-x"
    name: str    # e.g. "[stack]", "[heap]", "libc.so"

    @property
    def size(self) -> int:
        """SIMULATOR: Size of this VMA in bytes."""
        return self.end - self.start

    def contains(self, addr: int) -> bool:
        """SIMULATOR: Check whether addr falls within this VMA."""
        return self.start <= addr < self.end


class AddressSpace:
    """SIMULATOR: Models a process virtual address space."""

    def __init__(self, pid: int):
        """SIMULATOR: Create an empty address space for the given pid."""
        self.pid = pid
        self.areas: List[VirtualMemoryArea] = []

    def map(self, start: int, size: int, flags: str, name: str) -> VirtualMemoryArea:
        """SIMULATOR: Map a new VMA into this address space."""
        vma = VirtualMemoryArea(start=start, end=start + size, flags=flags, name=name)
        self.areas.append(vma)
        return vma

    def unmap(self, start: int) -> bool:
        """SIMULATOR: Remove the VMA that starts at the given address."""
        before = len(self.areas)
        self.areas = [a for a in self.areas if a.start != start]
        return len(self.areas) < before

    def lookup(self, addr: int) -> Optional[VirtualMemoryArea]:
        """SIMULATOR: Find the VMA that contains the given address."""
        for vma in self.areas:
            if vma.contains(addr):
                return vma
        return None

    def check_access(self, addr: int, write: bool = False, exec: bool = False) -> bool:
        """SIMULATOR: Simulate access permission check (would cause page fault if fails)."""
        vma = self.lookup(addr)
        if vma is None:
            return False
        flags = vma.flags
        if write and 'w' not in flags:
            return False
        if exec and 'x' not in flags:
            return False
        return True


class VirtualMemoryManager:
    """SIMULATOR: Models the kernel virtual memory manager.

    In a real kernel, the VMM maintains page tables for each process address space
    (PML4 -> PDPT -> PD -> PT on x86_64) and handles page faults to implement
    demand paging, copy-on-write, and memory-mapped files.
    """

    def __init__(self, pmm: PhysicalMemoryManager, logger: KernelLogger):
        """SIMULATOR: Create a VMM backed by the given PMM."""
        self._pmm = pmm
        self._logger = logger
        self.address_spaces: Dict[int, AddressSpace] = {}

    def create_address_space(self, pid: int) -> AddressSpace:
        """SIMULATOR: Create a new virtual address space for a process."""
        as_ = AddressSpace(pid)
        # Add default VMAs
        as_.map(0x400000, 0x1000, "r-x", "[text]")
        as_.map(0x600000, 0x1000, "rw-", "[data]")
        as_.map(0x00007fff00000000, 0x100000, "rw-", "[stack]")
        self.address_spaces[pid] = as_
        self._logger.debug("MM", f"create_address_space: pid={pid}")
        return as_

    def destroy_address_space(self, pid: int):
        """SIMULATOR: Destroy a process address space, freeing all pages."""
        self.address_spaces.pop(pid, None)
        self._logger.debug("MM", f"destroy_address_space: pid={pid}")

    def map_pages(self, pid: int, vaddr: int, size: int, flags: str, name: str) -> bool:
        """SIMULATOR: Map pages into a process's address space."""
        as_ = self.address_spaces.get(pid)
        if as_ is None:
            self._logger.error("MM", f"map_pages: unknown pid={pid}")
            return False
        pages_needed = (size + PAGE_SIZE - 1) // PAGE_SIZE
        pages = self._pmm.alloc_pages(pages_needed, pid)
        if not pages:
            self._logger.error("MM", f"map_pages: OOM for pid={pid}")
            return False
        as_.map(vaddr, size, flags, name)
        self._logger.info("MM", f"map_pages: pid={pid} vaddr=0x{vaddr:016x} size={size} flags={flags} name={name}")
        return True

    def unmap_pages(self, pid: int, vaddr: int) -> bool:
        """SIMULATOR: Unmap a VMA from a process's address space."""
        as_ = self.address_spaces.get(pid)
        if as_ is None:
            return False
        result = as_.unmap(vaddr)
        if result:
            self._logger.info("MM", f"unmap_pages: pid={pid} vaddr=0x{vaddr:016x}")
        return result

    def simulate_page_fault(self, pid: int, addr: int, write: bool = False) -> str:
        """SIMULATOR: Simulate a page fault for educational purposes.

        In a real kernel, a page fault (#PF, vector 14) fires when:
        - Page not present (demand paging)
        - Write to read-only page (COW or protection fault)
        - User-mode access to kernel page (SMAP violation)
        - Execute from NX page
        The fault handler checks VMAs, allocates/maps the page, or sends SIGSEGV.
        """
        as_ = self.address_spaces.get(pid)
        if as_ is None:
            return f"#PF: pid={pid} not found -> unhandled fault"
        vma = as_.lookup(addr)
        if vma is None:
            return (
                f"#PF: pid={pid} addr=0x{addr:016x} -> no VMA found "
                f"-> would deliver SIGSEGV (segmentation fault)"
            )
        if write and 'w' not in vma.flags:
            return (
                f"#PF: pid={pid} addr=0x{addr:016x} write to read-only VMA '{vma.name}' "
                f"-> protection fault -> SIGSEGV"
            )
        return (
            f"#PF: pid={pid} addr=0x{addr:016x} in VMA '{vma.name}' flags={vma.flags} "
            f"-> demand page satisfied (simulated alloc)"
        )


class KmallocAllocator:
    """SIMULATOR: Models the kernel slab/kmalloc allocator.

    In a real kernel, kmalloc() allocates small kernel objects from per-CPU
    slab caches (SLUB allocator in Linux). Objects of similar size share a cache
    to reduce fragmentation and improve cache locality.
    Here we just track fake addresses and sizes.
    """

    def __init__(self, logger: KernelLogger):
        """SIMULATOR: Create a kmalloc allocator starting at a simulated kernel address."""
        self._logger = logger
        self._allocations: Dict[int, int] = {}  # addr -> size
        self._next_addr = KERNEL_BASE + 0x1000000  # start well above kernel base

    def alloc(self, size: int) -> int:
        """SIMULATOR: Allocate kernel memory, returns fake virtual address."""
        if size <= 0:
            raise ValueError("kmalloc: invalid size")
        addr = self._next_addr
        self._next_addr += (size + 15) & ~15  # 16-byte aligned
        self._allocations[addr] = size
        self._logger.debug("MM", f"kmalloc: size={size} -> addr=0x{addr:016x}")
        return addr

    def free(self, addr: int):
        """SIMULATOR: Free kernel memory."""
        if addr in self._allocations:
            size = self._allocations.pop(addr)
            self._logger.debug("MM", f"kfree: addr=0x{addr:016x} size={size}")
        else:
            self._logger.warn("MM", f"kfree: unknown addr=0x{addr:016x} (double free?)")

    def usage(self) -> dict:
        """SIMULATOR: Return current allocator usage statistics."""
        total = sum(self._allocations.values())
        return {
            "allocations": len(self._allocations),
            "bytes_allocated": total,
            "next_addr": hex(self._next_addr),
        }
