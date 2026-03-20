"""
ComputeKERNEL-Edu: Educational Python simulator of a UNIX-like kernel architecture.

DISCLAIMER: This is a purely educational simulator. It does NOT run on bare metal,
does NOT execute privileged CPU instructions, and does NOT implement a real operating
system kernel. All kernel concepts are modeled in Python userspace for learning only.
"""

from computekernel_edu.shell import main

if __name__ == "__main__":
    main()
