"""Tests for the memory management simulation."""
import pytest
from computekernel_edu.memory import (
    PhysicalMemoryManager, VirtualMemoryManager, KmallocAllocator,
    PAGE_SIZE, KERNEL_BASE, USER_MAX,
)
from computekernel_edu.logger import KernelLogger


@pytest.fixture
def log():
    l = KernelLogger()
    l._serial_sink = False
    return l


def test_alloc_page(log):
    pmm = PhysicalMemoryManager(64, log)
    page = pmm.alloc_page(pid=1)
    assert page is not None
    assert page.in_use is True
    assert page.owner_pid == 1


def test_free_page(log):
    pmm = PhysicalMemoryManager(64, log)
    page = pmm.alloc_page(pid=1)
    pfn = page.pfn
    pmm.free_page(pfn)
    assert not pmm._pages[pfn].in_use


def test_oom(log):
    pmm = PhysicalMemoryManager(4, log)
    pages = [pmm.alloc_page(1) for _ in range(4)]
    assert all(p is not None for p in pages)
    oom = pmm.alloc_page(1)
    assert oom is None


def test_alloc_pages_batch(log):
    pmm = PhysicalMemoryManager(64, log)
    pages = pmm.alloc_pages(8, pid=2)
    assert len(pages) == 8
    assert pmm.free_pages == 56


def test_vmm_create_address_space(log):
    pmm = PhysicalMemoryManager(256, log)
    vmm = VirtualMemoryManager(pmm, log)
    as_ = vmm.create_address_space(pid=5)
    assert as_ is not None
    assert as_.pid == 5


def test_vmm_map_unmap(log):
    pmm = PhysicalMemoryManager(256, log)
    vmm = VirtualMemoryManager(pmm, log)
    vmm.create_address_space(pid=3)
    ok = vmm.map_pages(3, 0x500000, PAGE_SIZE * 4, "rw-", "heap")
    assert ok is True
    result = vmm.unmap_pages(3, 0x500000)
    assert result is True


def test_page_fault_no_vma(log):
    pmm = PhysicalMemoryManager(256, log)
    vmm = VirtualMemoryManager(pmm, log)
    vmm.create_address_space(pid=4)
    result = vmm.simulate_page_fault(4, 0xDEADBEEF)
    assert "SIGSEGV" in result or "no VMA" in result


def test_page_fault_write_readonly(log):
    pmm = PhysicalMemoryManager(256, log)
    vmm = VirtualMemoryManager(pmm, log)
    as_ = vmm.create_address_space(pid=6)
    as_.map(0x400000, 0x1000, "r-x", "text")
    result = vmm.simulate_page_fault(6, 0x400100, write=True)
    assert "protection fault" in result or "SIGSEGV" in result


def test_kmalloc(log):
    km = KmallocAllocator(log)
    addr1 = km.alloc(64)
    addr2 = km.alloc(128)
    assert addr1 != addr2
    assert addr1 >= KERNEL_BASE
    km.free(addr1)
    usage = km.usage()
    assert usage["allocations"] == 1
