"""
ComputeKERNEL-Edu: Educational Python simulator of a UNIX-like kernel architecture.

DISCLAIMER: This is a purely educational simulator. It does NOT run on bare metal,
does NOT execute privileged CPU instructions, and does NOT implement a real operating
system kernel. All kernel concepts (boot, memory management, scheduling, VFS, etc.)
are modeled in Python userspace for learning purposes only.

Real ComputeKERNEL targets x86_64, boots via GRUB2/Multiboot2, and is written in C.
This Python package simulates its architecture for educational exploration.
"""

__version__ = "0.1.0"
__project__ = "ComputeKERNEL-Edu"
__disclaimer__ = (
    "EDUCATIONAL SIMULATOR: Runs in Python userspace. "
    "Does not execute privileged instructions or boot on hardware."
)
