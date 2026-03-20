"""
SIMULATOR: Thread model.
Models kernel threads and user-space threads (tasks in Linux terms).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from .process import TaskState
from .logger import KernelLogger


@dataclass
class CpuContext:
    """SIMULATOR: Models x86_64 CPU register context saved on context switch.

    In a real kernel, context switch saves/restores: rax, rbx, rcx, rdx, rsi,
    rdi, rsp, rbp, r8-r15, rip, rflags, cs, ss, ds, es, fs, gs.
    Here these are just Python ints representing conceptual register values.
    """
    rax:    int = 0
    rbx:    int = 0
    rcx:    int = 0
    rdx:    int = 0
    rsi:    int = 0
    rdi:    int = 0
    rsp:    int = 0
    rbp:    int = 0
    rip:    int = 0
    rflags: int = 0x202  # IF set (interrupts enabled)
    cs:     int = 0x08   # kernel code segment
    ss:     int = 0x10   # kernel stack segment


@dataclass
class Thread:
    """SIMULATOR: Models a kernel task/thread (analogous to Linux task_struct)."""
    tid:              int
    pid:              int
    name:             str
    state:            TaskState  = TaskState.NEW
    cpu_context:      CpuContext = field(default_factory=CpuContext)
    timeslice:        int        = 10
    remaining_ticks:  int        = 10
    wait_reason:      str        = ""
    is_kernel_thread: bool       = False
    cpu_affinity:     int        = -1   # -1 = any CPU
    priority:         int        = 0    # higher = more priority


class TidAllocator:
    """SIMULATOR: TID (Thread ID) allocator."""

    def __init__(self):
        """SIMULATOR: Initialize TID allocator starting at 1."""
        self._next_tid = 1
        self._free_tids: List[int] = []

    def alloc(self) -> int:
        """SIMULATOR: Allocate the next available TID."""
        if self._free_tids:
            return self._free_tids.pop(0)
        tid = self._next_tid
        self._next_tid += 1
        return tid

    def free(self, tid: int):
        """SIMULATOR: Return a TID to the free pool."""
        self._free_tids.append(tid)


class ThreadTable:
    """SIMULATOR: Global thread table (like Linux's task list for threads)."""

    def __init__(self, logger: KernelLogger):
        """SIMULATOR: Create an empty thread table."""
        self._threads: Dict[int, Thread] = {}
        self._tid_alloc = TidAllocator()
        self._logger = logger

    def spawn(self, pid: int, name: str, timeslice: int = 10,
              is_kernel_thread: bool = False) -> Thread:
        """SIMULATOR: Create and register a new thread.

        Real kernel analog: kernel_thread() for kernel threads,
        or copy_process() with CLONE_THREAD for user threads.
        Sets up a CPU context (stack pointer, instruction pointer, segments).
        """
        tid = self._tid_alloc.alloc()
        ctx = CpuContext()
        # Simulate different stack/IP for kernel vs user threads
        if is_kernel_thread:
            ctx.cs = 0x08
            ctx.ss = 0x10
            ctx.rsp = 0xFFFF800000000000 + tid * 0x10000
        else:
            ctx.cs = 0x2B
            ctx.ss = 0x23
            ctx.rsp = 0x00007fff00000000 - tid * 0x10000
        t = Thread(
            tid=tid, pid=pid, name=name, state=TaskState.NEW,
            cpu_context=ctx, timeslice=timeslice, remaining_ticks=timeslice,
            is_kernel_thread=is_kernel_thread,
        )
        self._threads[tid] = t
        self._logger.debug("SCHED", f"thread_spawn: tid={tid} pid={pid} name={name}")
        return t

    def get(self, tid: int) -> Optional[Thread]:
        """SIMULATOR: Look up a thread by TID."""
        return self._threads.get(tid)

    def all(self) -> List[Thread]:
        """SIMULATOR: Return all threads."""
        return list(self._threads.values())

    def by_pid(self, pid: int) -> List[Thread]:
        """SIMULATOR: Return all threads belonging to a given process."""
        return [t for t in self._threads.values() if t.pid == pid]

    def remove(self, tid: int):
        """SIMULATOR: Remove a thread from the table and free its TID."""
        t = self._threads.pop(tid, None)
        if t:
            self._tid_alloc.free(tid)
