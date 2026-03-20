"""
SIMULATOR: Inter-process communication (IPC) subsystem.
Models pipes and signals.

Real kernel: Pipes are kernel buffers (typically 64KB) with read/write ends
exposed as file descriptors. Signals are asynchronous notifications delivered
to processes via the kernel's signal delivery mechanism (do_signal()).
"""

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional
from .logger import KernelLogger


class Signal(Enum):
    """SIMULATOR: POSIX signals."""
    SIGHUP   =  1  # hangup
    SIGTERM  = 15  # termination request
    SIGKILL  =  9  # force kill (cannot be caught)
    SIGCHLD  = 17  # child state changed
    SIGUSR1  = 10  # user-defined 1
    SIGUSR2  = 12  # user-defined 2
    SIGSEGV  = 11  # segmentation fault
    SIGINT   =  2  # interrupt from keyboard (^C)
    SIGSTOP  = 19  # stop process (cannot be caught)


@dataclass
class Pipe:
    """SIMULATOR: Models a kernel pipe (anonymous pipe).

    Real kernel: pipe() creates a VFS inode backed by a 64KB ring buffer.
    Read blocks when empty, write blocks when full (or returns EPIPE if reader closed).
    Here we use a Python deque.
    """
    read_fd:       int
    write_fd:      int
    _buffer:       deque = field(default_factory=lambda: deque(maxlen=65536))
    _write_closed: bool  = False
    _read_closed:  bool  = False

    def write(self, data: bytes) -> int:
        """SIMULATOR: Write bytes into the pipe buffer."""
        if self._write_closed or self._read_closed:
            return -32  # EPIPE
        for b in data:
            self._buffer.append(b)
        return len(data)

    def read(self, size: int) -> bytes:
        """SIMULATOR: Read bytes from the pipe buffer."""
        result = []
        for _ in range(min(size, len(self._buffer))):
            result.append(self._buffer.popleft())
        return bytes(result)

    def close_write(self):
        """SIMULATOR: Close the write end of the pipe."""
        self._write_closed = True

    def close_read(self):
        """SIMULATOR: Close the read end of the pipe."""
        self._read_closed = True

    @property
    def available(self) -> int:
        """SIMULATOR: Number of bytes available to read."""
        return len(self._buffer)


class SignalTable:
    """SIMULATOR: Per-process pending signal set."""

    def __init__(self, pid: int):
        """SIMULATOR: Create an empty signal table for the given pid."""
        self.pid = pid
        self._pending: List[Signal] = []
        self._blocked: set = set()  # blocked signal mask

    def send(self, sig: Signal):
        """SIMULATOR: Deliver a signal to this process.

        Real kernel: do_send_sig_info() adds to the task's pending signal set.
        SIGKILL and SIGSTOP cannot be blocked.
        """
        if sig not in self._blocked or sig in (Signal.SIGKILL, Signal.SIGSTOP):
            self._pending.append(sig)

    def has_pending(self) -> bool:
        """SIMULATOR: Check if there are any pending signals."""
        return bool(self._pending)

    def next_signal(self) -> Optional[Signal]:
        """SIMULATOR: Dequeue the next pending signal."""
        if self._pending:
            return self._pending.pop(0)
        return None

    def block(self, sig: Signal):
        """SIMULATOR: Block a signal (add to signal mask)."""
        self._blocked.add(sig)

    def unblock(self, sig: Signal):
        """SIMULATOR: Unblock a signal (remove from signal mask)."""
        self._blocked.discard(sig)


class IpcManager:
    """SIMULATOR: IPC manager - pipes and signals."""

    def __init__(self, logger: KernelLogger):
        """SIMULATOR: Create a new IPC manager."""
        self._logger = logger
        self._pipes: Dict[int, Pipe] = {}
        self._signal_tables: Dict[int, SignalTable] = {}
        self._next_pipe_fd = 100  # start pipe fds high to avoid collision

    def create_pipe(self) -> Pipe:
        """SIMULATOR: Create an anonymous pipe (like pipe2 syscall).

        Real kernel: alloc_file_pseudo() creates two struct file objects
        sharing a pipe_inode_info buffer of 16 pages (64KB by default).
        """
        read_fd  = self._next_pipe_fd
        write_fd = self._next_pipe_fd + 1
        self._next_pipe_fd += 2
        pipe = Pipe(read_fd=read_fd, write_fd=write_fd)
        self._pipes[read_fd]  = pipe
        self._pipes[write_fd] = pipe
        self._logger.debug("IPC", f"pipe created: read_fd={read_fd} write_fd={write_fd}")
        return pipe

    def get_pipe(self, fd: int) -> Optional[Pipe]:
        """SIMULATOR: Retrieve a pipe by one of its file descriptors."""
        return self._pipes.get(fd)

    def create_signal_table(self, pid: int) -> SignalTable:
        """SIMULATOR: Create a signal table for a new process."""
        table = SignalTable(pid)
        self._signal_tables[pid] = table
        return table

    def send_signal(self, pid: int, sig: Signal) -> bool:
        """SIMULATOR: Send a signal to a process (kill(2) syscall).

        Real kernel: kill_pid_info() -> group_send_sig_info() -> do_send_sig_info().
        Wakes up the target process if it is sleeping interruptibly.
        """
        table = self._signal_tables.get(pid)
        if table is None:
            self._logger.warn("IPC", f"send_signal: unknown pid={pid}")
            return False
        table.send(sig)
        self._logger.info("IPC", f"signal: pid={pid} sig={sig.name}")
        return True

    def has_pending_signals(self, pid: int) -> bool:
        """SIMULATOR: Check if a process has pending signals."""
        table = self._signal_tables.get(pid)
        return table is not None and table.has_pending()

    def next_signal(self, pid: int) -> Optional[Signal]:
        """SIMULATOR: Dequeue the next pending signal for a process."""
        table = self._signal_tables.get(pid)
        if table:
            return table.next_signal()
        return None
