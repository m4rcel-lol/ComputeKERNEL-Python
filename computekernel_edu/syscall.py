"""
SIMULATOR: Syscall table and dispatcher.
Models the system call interface between user-space and the kernel.

Real kernel: On x86_64, user-space invokes syscalls via the SYSCALL instruction.
The kernel entry point (entry_SYSCALL_64) saves registers, looks up the syscall
number in sys_call_table[], calls the handler, then returns via SYSRET.

SIMULATOR: We model 14 common syscalls with simulated behavior.
Error return convention: negative values are -errno (e.g. -2 = ENOENT).
"""

from typing import TYPE_CHECKING, Optional
from .logger import KernelLogger

if TYPE_CHECKING:
    from .process import ProcessTable
    from .thread import ThreadTable
    from .vfs import VFS
    from .memory import VirtualMemoryManager


# errno constants (negative = error return)
EPERM  =  1
ENOENT =  2
ESRCH  =  3
EBADF  =  9
ENOMEM = 12
EINVAL = 22
ENOSYS = 38


class SyscallDispatcher:
    """SIMULATOR: Kernel syscall dispatcher.

    Real kernel: sys_call_table[] maps syscall numbers to handler functions.
    The entry point (entry_SYSCALL_64) fetches rax (syscall number), verifies
    it is within bounds, and calls sys_call_table[rax](args...).
    Error codes are returned in rax as negated errno values.

    SIMULATOR: We implement 14 common syscalls using Python method dispatch.
    """

    # Syscall numbers (x86_64 ABI)
    NR_READ      =  0
    NR_WRITE     =  1
    NR_OPENAT    =  2
    NR_CLOSE     =  3
    NR_MMAP      =  9
    NR_MUNMAP    = 11
    NR_BRK       = 12
    NR_NANOSLEEP = 35
    NR_GETPID    = 39
    NR_FORK      = 57
    NR_EXECVE    = 59
    NR_EXIT      = 60
    NR_WAIT4     = 61
    NR_KILL      = 62

    def __init__(
        self,
        process_table: "ProcessTable",
        thread_table: "ThreadTable",
        vfs: "VFS",
        vmm: "VirtualMemoryManager",
        logger: KernelLogger,
    ):
        """SIMULATOR: Create the syscall dispatcher wired to kernel subsystems."""
        self._pt  = process_table
        self._tt  = thread_table
        self._vfs = vfs
        self._vmm = vmm
        self._logger = logger
        self._brk: dict = {}   # pid -> current brk

        # Build dispatch table
        self._table = {
            self.NR_READ:      self._sys_read,
            self.NR_WRITE:     self._sys_write,
            self.NR_OPENAT:    self._sys_openat,
            self.NR_CLOSE:     self._sys_close,
            self.NR_MMAP:      self._sys_mmap,
            self.NR_MUNMAP:    self._sys_munmap,
            self.NR_BRK:       self._sys_brk,
            self.NR_NANOSLEEP: self._sys_nanosleep,
            self.NR_GETPID:    self._sys_getpid,
            self.NR_FORK:      self._sys_fork,
            self.NR_EXECVE:    self._sys_execve,
            self.NR_EXIT:      self._sys_exit,
            self.NR_WAIT4:     self._sys_wait4,
            self.NR_KILL:      self._sys_kill,
        }

    def dispatch(self, pid: int, nr: int, *args) -> int:
        """SIMULATOR: Dispatch a syscall for the given process.

        Real kernel: entry_SYSCALL_64 -> syscall_enter_from_user_mode() ->
        sys_call_table[nr](regs) -> syscall_exit_to_user_mode().
        """
        handler = self._table.get(nr)
        if handler is None:
            self._logger.warn("SYSCALL", f"pid={pid} nr={nr}: ENOSYS (not implemented)")
            return -ENOSYS
        self._logger.debug("SYSCALL", f"pid={pid} syscall nr={nr} args={args}")
        return handler(pid, *args)

    # -------------------------------------------------------------------------
    # Individual syscall implementations
    # -------------------------------------------------------------------------

    def _sys_read(self, pid: int, fd: int, size: int = 4096) -> int:
        """SIMULATOR: sys_read(fd, buf, count) - read from file descriptor.

        Real kernel: vfs_read() -> file->f_op->read(). If the file is a pipe or
        socket, may block until data is available. Returns bytes read or -errno.
        """
        proc = self._pt.get(pid)
        if proc is None:
            return -EINVAL
        entry = proc.fdt.get(fd)
        if entry is None:
            self._logger.warn("SYSCALL", f"read: pid={pid} bad fd={fd}")
            return -EBADF
        data = self._vfs.read(fd, size)
        self._logger.debug("SYSCALL", f"read: pid={pid} fd={fd} got {len(data)} bytes")
        return len(data)

    def _sys_write(self, pid: int, fd: int, data: bytes = b"") -> int:
        """SIMULATOR: sys_write(fd, buf, count) - write to file descriptor.

        Real kernel: vfs_write() -> file->f_op->write(). For regular files
        writes go to the page cache. For O_SYNC, writeback is triggered immediately.
        """
        proc = self._pt.get(pid)
        if proc is None:
            return -EINVAL
        if fd in (1, 2):  # stdout/stderr: just log it
            text = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else str(data)
            self._logger.info("SYSCALL", f"write(stdout): pid={pid} '{text.strip()}'")
            return len(data) if data else 0
        entry = proc.fdt.get(fd)
        if entry is None:
            return -EBADF
        n = self._vfs.write(fd, data if isinstance(data, bytes) else str(data).encode())
        return n

    def _sys_openat(self, pid: int, dirfd: int = -100, path: str = "", flags: str = "r") -> int:
        """SIMULATOR: sys_openat(dirfd, pathname, flags, mode) - open a file.

        Real kernel: do_sys_openat2() -> build_open_flags() -> do_filp_open() ->
        path_openat(). The dirfd allows relative paths (AT_FDCWD = current dir).
        Returns a new file descriptor or -errno.
        """
        proc = self._pt.get(pid)
        if proc is None:
            return -EINVAL
        if not path:
            return -EINVAL
        fd = self._vfs.open(path, flags)
        if fd < 0:
            self._logger.warn("SYSCALL", f"openat: pid={pid} path='{path}' -> {fd}")
            return fd
        # Register in process fd table
        proc.fdt._table[fd] = (path, flags)
        self._logger.debug("SYSCALL", f"openat: pid={pid} path='{path}' -> fd={fd}")
        return fd

    def _sys_close(self, pid: int, fd: int) -> int:
        """SIMULATOR: sys_close(fd) - close a file descriptor.

        Real kernel: __close_fd() removes the fd from the fdtable and calls
        fput() to decrement the file's reference count.
        """
        proc = self._pt.get(pid)
        if proc is None:
            return -EINVAL
        if not proc.fdt.close(fd):
            return -EBADF
        self._vfs.close(fd)
        return 0

    def _sys_mmap(self, pid: int, addr: int = 0, length: int = 4096,
                  flags: str = "rw-", name: str = "[mmap]") -> int:
        """SIMULATOR: sys_mmap(addr, length, prot, flags, fd, offset) - map memory.

        Real kernel: ksys_mmap_pgoff() -> vm_mmap_pgoff() -> do_mmap() creates
        a new VMA in the process address space. For MAP_ANONYMOUS, it's backed
        by zero pages. For MAP_FILE, it maps the file's page cache.
        Returns the mapped virtual address or -errno.
        """
        if length <= 0:
            return -EINVAL
        proc = self._pt.get(pid)
        if proc is None:
            return -EINVAL
        # Choose address if not specified
        if addr == 0:
            as_ = self._vmm.address_spaces.get(pid)
            addr = 0x7f0000000000 if as_ is None else 0x7f0000000000
        ok = self._vmm.map_pages(pid, addr, length, flags, name)
        if not ok:
            return -ENOMEM
        self._logger.debug("SYSCALL", f"mmap: pid={pid} addr=0x{addr:x} len={length}")
        return addr

    def _sys_munmap(self, pid: int, addr: int = 0, length: int = 0) -> int:
        """SIMULATOR: sys_munmap(addr, length) - unmap memory.

        Real kernel: __do_munmap() splits or removes VMAs covering [addr, addr+length),
        flushes TLB, and frees the page table entries.
        """
        if addr == 0:
            return -EINVAL
        ok = self._vmm.unmap_pages(pid, addr)
        return 0 if ok else -EINVAL

    def _sys_brk(self, pid: int, new_brk: int = 0) -> int:
        """SIMULATOR: sys_brk(addr) - adjust program break (heap end).

        Real kernel: The program break marks the end of the heap. brk() extends
        or shrinks the heap VMA. Returns the new program break address.
        On failure (can't expand), returns the current break.
        """
        current = self._brk.get(pid, 0x601000)
        if new_brk == 0 or new_brk <= current:
            return current
        # Simulate extending heap
        size = new_brk - current
        self._vmm.map_pages(pid, current, size, "rw-", "[heap]")
        self._brk[pid] = new_brk
        self._logger.debug("SYSCALL", f"brk: pid={pid} 0x{current:x} -> 0x{new_brk:x}")
        return new_brk

    def _sys_nanosleep(self, pid: int, seconds: int = 0, nanos: int = 0) -> int:
        """SIMULATOR: sys_nanosleep(timespec) - sleep for a duration.

        Real kernel: hrtimer_nanosleep() sets up a high-resolution timer and
        calls schedule(). The process goes to TASK_INTERRUPTIBLE sleep until
        the timer fires or a signal is delivered.
        SIMULATOR: We just log the sleep request; no actual blocking occurs.
        """
        self._logger.debug("SYSCALL", f"nanosleep: pid={pid} {seconds}s {nanos}ns (simulated, non-blocking)")
        return 0

    def _sys_getpid(self, pid: int) -> int:
        """SIMULATOR: sys_getpid() - return the caller's PID.

        Real kernel: Simply returns current->tgid (thread group ID = PID for the
        main thread). One of the simplest syscalls.
        """
        return pid

    def _sys_fork(self, pid: int) -> int:
        """SIMULATOR: sys_fork() - create a child process.

        Real kernel: do_fork() / _do_fork() -> copy_process():
        1. Allocates a new task_struct (dup_task_struct)
        2. Copies memory maps (copy_mm, copy-on-write)
        3. Copies file descriptors (copy_files)
        4. Copies signal handlers
        5. Allocates new PID
        6. Wakes up the new task
        Returns child PID to parent, 0 to child.
        SIMULATOR: We create a new process in the process table.
        """
        parent = self._pt.get(pid)
        if parent is None:
            return -EINVAL
        child = self._pt.spawn(
            name=parent.name,
            ppid=pid,
            uid=parent.creds.uid,
            gid=parent.creds.gid,
            cmdline=parent.cmdline,
        )
        child.cwd = parent.cwd
        # Create address space for child (COW in real kernel; we just create a fresh one)
        self._vmm.create_address_space(child.pid)
        self._logger.info("SYSCALL", f"fork: pid={pid} -> child pid={child.pid}")
        return child.pid

    def _sys_execve(self, pid: int, path: str = "", argv: list = None,
                    envp: list = None) -> int:
        """SIMULATOR: sys_execve(pathname, argv, envp) - execute a program.

        Real kernel: do_execve() -> do_execveat_common() -> search_binary_handler()
        calls binfmt_elf.load_binary() which: flushes the old address space,
        maps the new ELF segments, sets up the stack with argv/envp/aux vectors,
        and returns to the new entry point.
        SIMULATOR: We just log the exec and update the process name.
        """
        proc = self._pt.get(pid)
        if proc is None:
            return -EINVAL
        proc.name = path.split("/")[-1] if path else proc.name
        proc.cmdline = path
        self._logger.info("SYSCALL", f"execve: pid={pid} path='{path}' argv={argv}")
        return 0

    def _sys_exit(self, pid: int, code: int = 0) -> int:
        """SIMULATOR: sys_exit(status) - terminate the calling process.

        Real kernel: do_exit() -> exit_mm() (releases memory maps), exit_files()
        (closes file descriptors), exit_signals(), __exit_signal(), do_task_dead().
        The process becomes a zombie until the parent calls wait().
        """
        from .process import TaskState
        proc = self._pt.get(pid)
        if proc is None:
            return -EINVAL
        proc.state = TaskState.ZOMBIE
        proc.exit_code = code
        self._logger.info("SYSCALL", f"exit: pid={pid} code={code}")
        return 0

    def _sys_wait4(self, pid: int, child_pid: int = -1, options: int = 0) -> int:
        """SIMULATOR: sys_wait4(pid, status, options, rusage) - wait for child.

        Real kernel: do_wait() sleeps until a child changes state (exits, stops,
        continues). It reaps zombie children by calling release_task().
        Returns the child PID that changed state, or -errno.
        SIMULATOR: We look for zombie children and reap them.
        """
        parent = self._pt.get(pid)
        if parent is None:
            return -EINVAL

        # Find a zombie child
        for child_pid_c in list(parent.children):
            child = self._pt.get(child_pid_c)
            if child is None:
                continue
            from .process import TaskState
            if child.state == TaskState.ZOMBIE:
                exit_code = child.exit_code
                self._pt.remove(child_pid_c)
                self._logger.info("SYSCALL", f"wait4: pid={pid} reaped child={child_pid_c} exit={exit_code}")
                return child_pid_c

        self._logger.debug("SYSCALL", f"wait4: pid={pid} no zombie children")
        return 0

    def _sys_kill(self, pid: int, target_pid: int = 0, signum: int = 15) -> int:
        """SIMULATOR: sys_kill(pid, sig) - send signal to process.

        Real kernel: kill_something_info() -> kill_pid_info() -> do_send_sig_info().
        Checks that the sender has permission to signal the target (same uid or root).
        SIGKILL/SIGSTOP cannot be blocked or ignored.
        """
        from .ipc import Signal
        target = self._pt.get(target_pid)
        if target is None:
            self._logger.warn("SYSCALL", f"kill: target pid={target_pid} not found")
            return -ESRCH

        # Map signum to Signal enum
        sig_map = {s.value: s for s in Signal}
        sig = sig_map.get(signum)
        if sig is None:
            return -EINVAL

        self._logger.info("SYSCALL", f"kill: pid={pid} -> target={target_pid} sig={sig.name}")
        # We don't have ipc here, just log the action
        return 0


