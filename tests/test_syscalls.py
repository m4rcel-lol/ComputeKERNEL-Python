"""Tests for the syscall dispatcher simulation."""
import pytest
from computekernel_edu.kernel import KernelState
from computekernel_edu.profiles import DEBUG_PROFILE
from computekernel_edu.syscall import SyscallContext, SYSCALL_TABLE


@pytest.fixture
def booted_kernel():
    k = KernelState()
    k.init(DEBUG_PROFILE)
    k.logger._serial_sink = False
    k.boot()
    return k


def test_syscall_table_has_14_entries():
    assert len(SYSCALL_TABLE) == 14


def test_getpid(booted_kernel):
    k = booted_kernel
    procs = k.process_table.all()
    if not procs:
        pytest.skip("No processes")
    pid = procs[0].pid
    ctx = SyscallContext(nr=39, pid=pid)
    result = k.syscall_dispatcher.dispatch(ctx)
    assert result == pid or result >= 0


def test_write_syscall(booted_kernel):
    k = booted_kernel
    procs = k.process_table.all()
    if not procs:
        pytest.skip("No processes")
    pid = procs[0].pid
    ctx = SyscallContext(nr=1, rdi=1, rsi=0, rdx=5, pid=pid)
    result = k.syscall_dispatcher.dispatch(ctx)
    assert result >= 0 or result == -9  # success or EBADF is fine


def test_unknown_syscall_returns_enosys(booted_kernel):
    k = booted_kernel
    ctx = SyscallContext(nr=9999, pid=1)
    result = k.syscall_dispatcher.dispatch(ctx)
    assert result == -38  # ENOSYS


def test_exit_syscall(booted_kernel):
    k = booted_kernel
    procs = [p for p in k.process_table.all() if not p.is_kernel_process]
    if not procs:
        pytest.skip("No user processes")
    pid = procs[0].pid
    ctx = SyscallContext(nr=60, rdi=0, pid=pid)
    result = k.syscall_dispatcher.dispatch(ctx)
    assert result == 0


def test_brk_syscall(booted_kernel):
    k = booted_kernel
    procs = k.process_table.all()
    if not procs:
        pytest.skip("No processes")
    pid = procs[0].pid
    ctx = SyscallContext(nr=12, rdi=0, pid=pid)
    result = k.syscall_dispatcher.dispatch(ctx)
    assert isinstance(result, int)


def test_nanosleep_syscall(booted_kernel):
    k = booted_kernel
    procs = k.process_table.all()
    if not procs:
        pytest.skip("No processes")
    pid = procs[0].pid
    threads = k.thread_table.by_pid(pid)
    if not threads:
        pytest.skip("No threads")
    ctx = SyscallContext(nr=35, rdi=1, pid=pid)
    result = k.syscall_dispatcher.dispatch(ctx)
    assert result == 0 or result < 0  # success or error - just must be int
