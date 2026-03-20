"""
SIMULATOR: Process model.
Models kernel process/task structures (analogous to Linux task_struct).

Real kernel: Each process is represented by a task_struct in the kernel.
The task_struct contains scheduling info, memory maps, file descriptors,
credentials, signal handlers, and much more.

SIMULATOR: We use Python dataclasses to represent simplified versions
of these kernel data structures for educational purposes.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional


class TaskState(Enum):
    """SIMULATOR: Process/thread states (analogous to Linux task states).

    Real kernel states:
      TASK_RUNNING       - runnable (on run queue) or actually running on CPU
      TASK_INTERRUPTIBLE - sleeping, can be woken by signal
      TASK_UNINTERRUPTIBLE - sleeping, ignores signals (e.g. waiting for I/O)
      TASK_ZOMBIE        - exited, waiting for parent to call wait()
      TASK_DEAD          - fully reaped
    """
    NEW         = auto()   # not yet added to scheduler
    RUNNABLE    = auto()   # TASK_RUNNING (on run queue, not yet on CPU)
    RUNNING     = auto()   # TASK_RUNNING (currently executing on a CPU)
    SLEEP_INT   = auto()   # TASK_INTERRUPTIBLE (waiting, can be signaled)
    SLEEP_UNINT = auto()   # TASK_UNINTERRUPTIBLE (deep sleep, no signals)
    ZOMBIE      = auto()   # exited, awaiting wait() from parent
    DEAD        = auto()   # fully reaped


@dataclass
class Credentials:
    """SIMULATOR: Process credentials (uid/gid/euid/egid).

    Real kernel: struct cred contains uid_t, gid_t, euid_t, egid_t,
    capability sets (cap_permitted, cap_effective, cap_inheritable),
    security labels (LSM), and reference counting.
    SIMULATOR: We just track the four basic POSIX IDs.
    """
    uid:  int = 0   # real user ID
    gid:  int = 0   # real group ID
    euid: int = 0   # effective user ID (used for permission checks)
    egid: int = 0   # effective group ID

    @property
    def is_root(self) -> bool:
        """SIMULATOR: True if effective UID is 0 (root)."""
        return self.euid == 0


@dataclass
class FileDescriptorTable:
    """SIMULATOR: Process file descriptor table.

    Real kernel: The fd table (struct files_struct) maps small non-negative
    integers (file descriptors) to open file descriptions (struct file).
    It also stores the close-on-exec bitmap.
    SIMULATOR: We map fd -> (path, flags) for simplicity.
    """
    _table: Dict[int, tuple] = field(default_factory=dict)
    _next_fd: int = 3  # 0/1/2 = stdin/stdout/stderr

    def alloc(self, path: str, flags: str = "r") -> int:
        """SIMULATOR: Allocate a new file descriptor."""
        fd = self._next_fd
        self._next_fd += 1
        self._table[fd] = (path, flags)
        return fd

    def get(self, fd: int) -> Optional[tuple]:
        """SIMULATOR: Retrieve the (path, flags) for a file descriptor."""
        return self._table.get(fd)

    def close(self, fd: int) -> bool:
        """SIMULATOR: Close and remove a file descriptor."""
        if fd in self._table:
            del self._table[fd]
            return True
        return False

    def all_fds(self) -> List[int]:
        """SIMULATOR: Return all open file descriptor numbers."""
        return list(self._table.keys())


@dataclass
class Process:
    """SIMULATOR: Kernel process descriptor (simplified task_struct).

    The Linux task_struct is ~8KB of fields. This is a dramatically simplified
    educational model capturing the most important concepts.
    """
    pid:        int
    ppid:       int          # parent PID
    name:       str          # process name (comm field in Linux)
    state:      TaskState    = field(default=TaskState.NEW)
    creds:      Credentials  = field(default_factory=Credentials)
    fdt:        FileDescriptorTable = field(default_factory=FileDescriptorTable)
    exit_code:  int          = 0
    cwd:        str          = "/"
    cmdline:    str          = ""
    children:   List[int]    = field(default_factory=list)   # child PIDs

    @property
    def is_kernel_process(self) -> bool:
        """SIMULATOR: True if this is a kernel process (pid 0 or ppid 0 kernel threads)."""
        return self.pid == 0 or (self.ppid == 0 and self.pid <= 2)

    @property
    def is_root(self) -> bool:
        """SIMULATOR: True if the process runs as root (euid=0)."""
        return self.creds.is_root

    def __repr__(self) -> str:
        return f"Process(pid={self.pid}, name={self.name!r}, state={self.state.name})"


class PidAllocator:
    """SIMULATOR: PID (Process ID) allocator.

    Real kernel: PIDs are allocated from a bitmap (pid_namespace) with a
    maximum of PID_MAX_DEFAULT (32768 on 32-bit, 4194304 on 64-bit).
    Freed PIDs are reused after cycling through the range.
    SIMULATOR: Simple incrementing allocator with free list.
    """

    def __init__(self):
        """SIMULATOR: Initialize PID allocator (PID 0 and 1 are reserved)."""
        self._next_pid = 2  # 0=swapper/idle, 1=init
        self._free_pids: List[int] = []

    def alloc(self) -> int:
        """SIMULATOR: Allocate the next available PID."""
        if self._free_pids:
            return self._free_pids.pop(0)
        pid = self._next_pid
        self._next_pid += 1
        return pid

    def free(self, pid: int):
        """SIMULATOR: Return a PID to the free pool."""
        if pid > 1:
            self._free_pids.append(pid)


class ProcessTable:
    """SIMULATOR: Global process table (like Linux's task list / PID hash table).

    In a real kernel, processes are linked via task_struct.tasks (a circular
    doubly-linked list) and also hashed by PID for O(1) lookup.
    We use a Python dict for O(1) PID lookup.
    """

    def __init__(self):
        """SIMULATOR: Initialize process table with the idle process (PID 0)."""
        self._table: Dict[int, Process] = {}
        self._pid_alloc = PidAllocator()

        # PID 0: swapper/idle - the kernel idle task, always exists
        idle = Process(pid=0, ppid=0, name="swapper/0",
                       state=TaskState.RUNNABLE,
                       creds=Credentials(uid=0, gid=0, euid=0, egid=0))
        self._table[0] = idle

    def spawn(self, name: str, ppid: int = 0,
              uid: int = 0, gid: int = 0,
              cmdline: str = "") -> Process:
        """SIMULATOR: Create a new process and add it to the process table.

        Real kernel analog: do_fork() / copy_process() - copies the parent's
        task_struct, creates new PID, copies memory maps (COW), file descriptors,
        and signal handlers. Adds the new task to the task list and scheduler.
        SIMULATOR: We allocate a PID and create a fresh Process.
        """
        pid = self._pid_alloc.alloc()
        creds = Credentials(uid=uid, gid=gid, euid=uid, egid=gid)
        proc = Process(
            pid=pid, ppid=ppid, name=name,
            state=TaskState.NEW,
            creds=creds,
            cmdline=cmdline,
        )
        self._table[pid] = proc
        # Register as child of parent
        if ppid in self._table:
            self._table[ppid].children.append(pid)
        return proc

    def get(self, pid: int) -> Optional[Process]:
        """SIMULATOR: Look up a process by PID."""
        return self._table.get(pid)

    def all(self) -> List[Process]:
        """SIMULATOR: Return all processes (like iterating task list)."""
        return list(self._table.values())

    def remove(self, pid: int):
        """SIMULATOR: Remove a process from the table (after reaping).

        Real kernel: Called from release_task() after wait() has reaped the zombie.
        Decrements reference count, frees task_struct, recycles PID.
        """
        proc = self._table.pop(pid, None)
        if proc:
            self._pid_alloc.free(pid)
            # Remove from parent's children list
            if proc.ppid in self._table:
                parent = self._table[proc.ppid]
                if pid in parent.children:
                    parent.children.remove(pid)

    def zombies(self) -> List[Process]:
        """SIMULATOR: Return all zombie processes awaiting reaping."""
        return [p for p in self._table.values() if p.state == TaskState.ZOMBIE]

    def by_name(self, name: str) -> List[Process]:
        """SIMULATOR: Find processes by name."""
        return [p for p in self._table.values() if p.name == name]
