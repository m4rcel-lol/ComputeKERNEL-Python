"""
SIMULATOR: Preemptive round-robin scheduler.
Models the scheduler subsystem of ComputeKERNEL.

Real kernel: The scheduler runs on timer interrupt (IRQ0/HPET/LAPIC timer),
picks the next runnable thread via a scheduling policy (CFS, round-robin, etc.),
performs a context switch (saves/restores CPU registers), and updates accounting.

SIMULATOR: We simulate ticks manually. No real timer interrupts occur.
Context "switches" are just Python attribute changes.

ComputeKERNEL MVP uses preemptive round-robin scheduling.
"""

from typing import List, Optional
from .thread import Thread, ThreadTable
from .process import TaskState
from .logger import KernelLogger


class Scheduler:
    """SIMULATOR: Preemptive round-robin scheduler.

    In a real kernel this would be driven by timer interrupts (IRQ0/HPET/LAPIC timer).
    Here we simulate ticks manually via tick() / tick_n().

    ComputeKERNEL uses a preemptive round-robin MVP scheduler.
    """

    DEFAULT_TIMESLICE = 10  # ticks per quantum

    def __init__(self, logger: KernelLogger):
        """SIMULATOR: Create a new scheduler with an empty run queue."""
        self.runqueue: List[Thread] = []
        self.current_thread: Optional[Thread] = None
        self.idle_thread: Optional[Thread] = None
        self.tick_count: int = 0
        self._logger = logger
        self._context_switches: int = 0
        self._blocked: List[Thread] = []

    def init(self, thread_table: ThreadTable):
        """SIMULATOR: Initialize scheduler, create the idle thread.

        Real kernel analog: sched_init() creates the per-CPU run queues and
        creates the idle task (pid 0 / swapper). The idle task runs the HLT
        instruction when there is nothing else to schedule.
        """
        idle = thread_table.spawn(pid=0, name="[idle]", timeslice=1, is_kernel_thread=True)
        idle.state = TaskState.RUNNABLE
        self.idle_thread = idle
        self._logger.info("SCHED", "Scheduler initialized. Idle thread created (tid=0 conceptual).")

    def add_thread(self, thread: Thread):
        """SIMULATOR: Add thread to the run queue (make runnable).

        Real kernel analog: wake_up_process() / activate_task() adds the task
        to the appropriate CPU's run queue.
        """
        thread.state = TaskState.RUNNABLE
        if thread not in self.runqueue:
            self.runqueue.append(thread)
            self._logger.debug("SCHED", f"add_thread: tid={thread.tid} name={thread.name}")

    def remove_thread(self, tid: int):
        """SIMULATOR: Remove thread from run queue."""
        self.runqueue = [t for t in self.runqueue if t.tid != tid]
        self._logger.debug("SCHED", f"remove_thread: tid={tid}")

    def block_thread(self, tid: int, reason: str = "io_wait"):
        """SIMULATOR: Block a thread (move to sleep state).

        Real kernel analog: set_current_state(TASK_INTERRUPTIBLE) followed by
        schedule() - the task removes itself from the run queue and yields CPU.
        """
        for t in list(self.runqueue):
            if t.tid == tid:
                t.state = TaskState.SLEEP_INT
                t.wait_reason = reason
                self.runqueue.remove(t)
                self._blocked.append(t)
                self._logger.debug("SCHED", f"block_thread: tid={tid} reason={reason}")
                if self.current_thread and self.current_thread.tid == tid:
                    self.current_thread = None
                return
        self._logger.warn("SCHED", f"block_thread: tid={tid} not in runqueue")

    def wake_thread(self, tid: int):
        """SIMULATOR: Wake a blocked thread.

        Real kernel analog: wake_up() / wake_up_process() sets the task state
        to TASK_RUNNING and re-adds it to the run queue, potentially triggering
        a preemption if the newly woken task has higher priority.
        """
        for t in list(self._blocked):
            if t.tid == tid:
                t.state = TaskState.RUNNABLE
                t.wait_reason = ""
                self._blocked.remove(t)
                self.runqueue.append(t)
                self._logger.debug("SCHED", f"wake_thread: tid={tid}")
                return
        self._logger.warn("SCHED", f"wake_thread: tid={tid} not in blocked list")

    def tick(self) -> Optional[Thread]:
        """SIMULATOR: Advance one scheduler tick. Returns the currently running thread.

        Real kernel analog: timer interrupt handler -> scheduler_tick() ->
        check if preemption needed -> schedule() -> context_switch().
        The timer interrupt fires at HZ frequency (100/250/1000 Hz in Linux).
        Each tick decrements the current task's time slice. When it reaches zero,
        the TIF_NEED_RESCHED flag is set and schedule() is called on interrupt return.
        """
        self.tick_count += 1

        if not self.runqueue:
            self.current_thread = self.idle_thread
            return self.idle_thread

        if self.current_thread is None or self.current_thread not in self.runqueue:
            # Pick first runnable
            self.current_thread = self.runqueue[0]
            self.current_thread.state = TaskState.RUNNING
            self.current_thread.remaining_ticks = self.current_thread.timeslice

        self.current_thread.remaining_ticks -= 1

        if self.current_thread.remaining_ticks <= 0:
            # Timeslice expired - rotate (round-robin)
            old = self.current_thread
            old.state = TaskState.RUNNABLE
            old.remaining_ticks = old.timeslice
            if old in self.runqueue:
                self.runqueue.remove(old)
                self.runqueue.append(old)
            if self.runqueue:
                self.current_thread = self.runqueue[0]
                self.current_thread.state = TaskState.RUNNING
                self.current_thread.remaining_ticks = self.current_thread.timeslice
                self._context_switches += 1
                self._logger.debug(
                    "SCHED",
                    f"context_switch: {old.name}(tid={old.tid}) -> "
                    f"{self.current_thread.name}(tid={self.current_thread.tid}) "
                    f"tick={self.tick_count}"
                )
            else:
                self.current_thread = self.idle_thread

        return self.current_thread

    def tick_n(self, n: int):
        """SIMULATOR: Advance n scheduler ticks."""
        for _ in range(n):
            self.tick()

    def status(self) -> dict:
        """SIMULATOR: Return current scheduler status."""
        return {
            "tick_count": self.tick_count,
            "context_switches": self._context_switches,
            "runqueue_length": len(self.runqueue),
            "blocked_count": len(self._blocked),
            "current_thread": (
                f"{self.current_thread.name}(tid={self.current_thread.tid})"
                if self.current_thread else "idle"
            ),
            "runqueue": [
                f"{t.name}(tid={t.tid}, ticks_left={t.remaining_ticks})"
                for t in self.runqueue
            ],
            "blocked": [
                f"{t.name}(tid={t.tid}, reason={t.wait_reason})"
                for t in self._blocked
            ],
        }
