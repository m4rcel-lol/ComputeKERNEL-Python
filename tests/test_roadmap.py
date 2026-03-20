"""Tests for roadmap feature coverage."""

from computekernel_edu.roadmap import ROADMAP, format_roadmap


EXPECTED_ROADMAP = [
    ("TCP/IP network stack", "In-kernel TCP/IP (lwIP or custom)"),
    ("Network device driver model", "NIC driver framework"),
    ("SSH daemon", "In-kernel SSH service"),
    ("SMP (multi-core) support", "Per-CPU scheduler, IPI, spinlocks"),
    ("ACPI power management", "Full ACPI AML interpreter"),
    ("USB stack", "xHCI host controller + USB drivers"),
    ("NVMe driver", "PCIe NVMe block device driver"),
    ("ext4 filesystem", "Full ext4 with journaling"),
    ("procfs / sysfs", "Runtime kernel info filesystems"),
    ("Memory-mapped files", "mmap(MAP_FILE) with page cache"),
    ("Copy-on-write fork", "Real COW fork() implementation"),
    ("POSIX threads (pthreads)", "Full pthread support"),
    ("ASLR", "Address space layout randomization"),
    ("KVM hypervisor support", "Paravirtualization"),
    ("DRM/KMS graphics", "Framebuffer + GPU driver model"),
    ("Audio subsystem", "ALSA-style audio model"),
    ("Bluetooth stack", "HCI/L2CAP model"),
    ("SELinux/AppArmor model", "Mandatory access control"),
    ("eBPF subsystem", "In-kernel safe programs"),
    ("io_uring", "Async I/O interface"),
]


def test_roadmap_includes_required_items_as_planned():
    required = {(name, detail) for name, detail in EXPECTED_ROADMAP}
    actual = {(name, detail) for name, detail, status in ROADMAP if status == "Planned"}
    assert required.issubset(actual)


def test_format_roadmap_lists_required_items_as_unchecked():
    text = format_roadmap()
    for name, detail in EXPECTED_ROADMAP:
        assert f"[ ] {name}" in text
        assert detail in text
