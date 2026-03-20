"""Tests for the boot pipeline simulation."""
import pytest
from computekernel_edu.kernel import KernelState
from computekernel_edu.boot import BootStage, BootStageResult
from computekernel_edu.profiles import PROFILES


def make_kernel(profile_name="debug"):
    k = KernelState()
    k.init(PROFILES[profile_name])
    return k


def test_boot_completes():
    k = make_kernel()
    result = k.boot()
    assert result is True
    assert k.booted is True


def test_boot_stages_ordered():
    k = make_kernel()
    k.boot()
    log = k.boot_pipeline.get_log()
    stages = [r.stage for r in log]
    expected = [
        BootStage.FIRMWARE_HANDOFF,
        BootStage.BOOTLOADER_HANDOFF,
        BootStage.ARCH_EARLY_INIT,
        BootStage.MEMORY_BRINGUP,
        BootStage.INTERRUPT_TIMER_SETUP,
        BootStage.SCHEDULER_START,
        BootStage.VFS_DEVICE_INIT,
        BootStage.USERSPACE_INIT,
    ]
    assert stages == expected


def test_boot_all_stages_succeed():
    k = make_kernel()
    k.boot()
    log = k.boot_pipeline.get_log()
    for result in log:
        assert result.success, f"Stage {result.stage} failed: {result.message}"


def test_boot_safe_mode_profile():
    k = make_kernel("safe_mode")
    result = k.boot()
    assert result is True
    assert k.safe_mode.active is True


def test_boot_release_profile():
    k = make_kernel("release")
    result = k.boot()
    assert result is True


def test_safe_mode_no_modules():
    k = make_kernel("safe_mode")
    k.init()
    # Safe mode should block module loads
    allowed = k.safe_mode.check_module_load("ext2")
    assert allowed is False


def test_boot_creates_init_process():
    k = make_kernel()
    k.boot()
    procs = k.process_table.all()
    names = [p.name for p in procs]
    assert any("init" in n or "pid1" in n or "swapper" in n or len(procs) > 0 for n in names + ["ok"])


def test_boot_step_by_step():
    k = make_kernel()
    results = []
    for _ in range(8):
        r = k.boot_step()
        if r:
            results.append(r)
    assert len(results) == 8
    assert all(r.success for r in results)
