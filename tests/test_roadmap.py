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
    roadmap_rows = [row for row in ROADMAP if (row[0], row[1]) in EXPECTED_ROADMAP]
    assert len(roadmap_rows) == len(EXPECTED_ROADMAP)
    assert len({(name, detail) for name, detail, _ in roadmap_rows}) == len(EXPECTED_ROADMAP)
    assert all(status == "Planned" for _, _, status in roadmap_rows)


def test_format_roadmap_lists_required_items_as_unchecked():
    lines = format_roadmap().splitlines()
    for name, detail in EXPECTED_ROADMAP:
        matching_lines = [line for line in lines if name in line and detail in line]
        assert len(matching_lines) == 1
        assert "[ ]" in matching_lines[0]
