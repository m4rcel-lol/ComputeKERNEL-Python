"""Tests for the round-robin scheduler simulation."""
import pytest
from computekernel_edu.scheduler import Scheduler
from computekernel_edu.thread import ThreadTable
from computekernel_edu.process import TaskState
from computekernel_edu.logger import KernelLogger


@pytest.fixture
def sched_env():
    log = KernelLogger()
    log._serial_sink = False
    tt = ThreadTable(log)
    sched = Scheduler(log)
    sched.init(tt)
    return sched, tt


def test_idle_when_empty(sched_env):
    sched, tt = sched_env
    result = sched.tick()
    assert result is sched.idle_thread


def test_add_thread_and_schedule(sched_env):
    sched, tt = sched_env
    t = tt.spawn(pid=1, name="proc1")
    sched.add_thread(t)
    current = sched.tick()
    assert current is t
    assert current.state == TaskState.RUNNING


def test_round_robin(sched_env):
    sched, tt = sched_env
    t1 = tt.spawn(pid=1, name="t1", timeslice=2)
    t2 = tt.spawn(pid=2, name="t2", timeslice=2)
    sched.add_thread(t1)
    sched.add_thread(t2)
    seen = set()
    for _ in range(10):
        cur = sched.tick()
        if cur:
            seen.add(cur.tid)
    assert len(seen) == 2


def test_block_wake(sched_env):
    sched, tt = sched_env
    t1 = tt.spawn(pid=1, name="t1")
    t2 = tt.spawn(pid=2, name="t2")
    sched.add_thread(t1)
    sched.add_thread(t2)
    sched.block_thread(t1.tid, "io_wait")
    assert t1.state == TaskState.SLEEP_INT
    assert t1 not in sched.runqueue
    sched.wake_thread(t1.tid)
    assert t1.state == TaskState.RUNNABLE
    assert t1 in sched.runqueue


def test_tick_count(sched_env):
    sched, tt = sched_env
    sched.tick_n(20)
    assert sched.tick_count == 20


def test_pid_allocator():
    from computekernel_edu.process import PidAllocator
    alloc = PidAllocator()
    p1 = alloc.alloc()
    p2 = alloc.alloc()
    assert p1 != p2
    alloc.free(p1)
    p3 = alloc.alloc()
    assert p3 == p1


def test_scheduler_status(sched_env):
    sched, tt = sched_env
    t = tt.spawn(pid=1, name="worker")
    sched.add_thread(t)
    sched.tick()
    status = sched.status()
    assert "runqueue_length" in status
    assert "tick_count" in status
    assert status["tick_count"] >= 1
