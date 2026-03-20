# ComputeKERNEL-Python

ComputeKERNEL-Python (package name: `computekernel-edu`) is an educational Python
simulator of a UNIX-like kernel architecture. It models concepts like boot,
memory management, scheduling, VFS, syscalls, and shell interaction for learning
purposes.

> This project is a simulator and does **not** run on bare metal hardware.

## Requirements

- Python 3.11+
- `pip`

## Quick start

```bash
python -m pip install .
python -m computekernel_edu --help
python -m computekernel_edu
```

You can also run the installed CLI entrypoint:

```bash
computekernel-edu --help
computekernel-edu
```

## Platform-specific installation and usage

For complete step-by-step instructions on downloading, installing, and running on:

- Windows
- Linux
- macOS

see: **[`docs/INSTALLATION.md`](docs/INSTALLATION.md)**.
