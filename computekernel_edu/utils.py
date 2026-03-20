"""
SIMULATOR: Utility functions for ComputeKERNEL-Edu.
"""

import shutil


def hex_addr(addr: int) -> str:
    """Format an address as 64-bit hex."""
    return f"0x{addr:016x}"


def hex_short(addr: int) -> str:
    """Format as short hex."""
    return f"0x{addr:08x}"


def size_fmt(n: int) -> str:
    """Human-readable byte size."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n //= 1024
    return f"{n} PB"


def validate_addr(addr: int) -> bool:
    """Check if an address is in a plausible user or kernel range."""
    USER_MAX    = 0x00007FFFFFFFFFFF
    KERNEL_BASE = 0xFFFF800000000000
    KERNEL_MAX  = 0xFFFFFFFFFFFFFFFF
    return (0 < addr <= USER_MAX) or (KERNEL_BASE <= addr <= KERNEL_MAX)


def table(headers: list, rows: list, col_widths: list | None = None) -> str:
    """SIMULATOR: Format a simple ASCII table."""
    if not col_widths:
        col_widths = [
            max(len(str(h)), max((len(str(r[i])) for r in rows), default=0))
            for i, h in enumerate(headers)
        ]
    sep = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"

    def fmt_row(row):
        cells = [f" {str(v):<{col_widths[i]}} " for i, v in enumerate(row)]
        return "|" + "|".join(cells) + "|"

    lines = [sep, fmt_row(headers), sep]
    for row in rows:
        lines.append(fmt_row(row))
    lines.append(sep)
    return "\n".join(lines)


# ANSI color helpers (gracefully disabled if not supported)
def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m"


def green(t: str) -> str:  return _c("32", t)
def red(t: str) -> str:    return _c("31", t)
def yellow(t: str) -> str: return _c("33", t)
def cyan(t: str) -> str:   return _c("36", t)
def bold(t: str) -> str:   return _c("1", t)
def dim(t: str) -> str:    return _c("2", t)
