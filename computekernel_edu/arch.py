"""
SIMULATOR: x86_64 architecture layer.
Models GDT, IDT, TSS, paging, and syscall entry setup.

IMPORTANT: ALL operations here are SIMULATED. No privileged instructions are executed,
no real descriptor tables are loaded (no LGDT/LIDT), no real page tables are set up.
In a real kernel, these operations run at ring-0 and directly configure CPU hardware.

Real ComputeKERNEL: written in C/ASM, runs on bare metal x86_64, uses LGDT/LIDT/LMSW,
writes CR0/CR3/CR4/EFER MSRs, programs LAPIC, programs IA32_LSTAR MSR for syscalls.
"""

from dataclasses import dataclass, field
from enum import IntEnum
from typing import List
from .logger import KernelLogger


@dataclass
class CpuFeatures:
    """SIMULATOR: CPU feature flags detected via CPUID instruction.

    In a real kernel, CPUID is executed with various leaf values to discover
    CPU capabilities. Here we model a capable x86_64 CPU with common features.
    """
    has_nx:             bool = True   # No-Execute (NX/XD) page bit (EFER.NXE)
    has_sse2:           bool = True   # SSE2 SIMD instructions
    has_avx2:           bool = True   # AVX2 256-bit SIMD
    has_rdrand:         bool = True   # Hardware RNG (RDRAND instruction)
    has_pae:            bool = True   # Physical Address Extension (>4GB physical memory)
    has_smep:           bool = True   # Supervisor Mode Execution Prevention (CR4.SMEP)
    has_smap:           bool = True   # Supervisor Mode Access Prevention (CR4.SMAP)
    has_pcid:           bool = True   # Process Context Identifiers (CR4.PCIDE, TLB tag)
    cores:              int  = 4      # Physical CPU cores
    threads_per_core:   int  = 2      # Hyper-threading threads per core


class PrivilegeRing(IntEnum):
    """SIMULATOR: x86 privilege rings encoded in segment descriptor DPL field.

    In real x86_64, only RING0 (kernel) and RING3 (user) are typically used.
    RING1 and RING2 exist in the ISA but are unused by modern OS kernels.
    """
    RING0 = 0  # Most privileged - kernel mode
    RING1 = 1  # Unused in practice
    RING2 = 2  # Unused in practice
    RING3 = 3  # Least privileged - user mode


KERNEL_RING = PrivilegeRing.RING0
USER_RING    = PrivilegeRing.RING3


@dataclass
class GdtEntry:
    """SIMULATOR: Global Descriptor Table entry.

    Real GDT entries are 8-byte structures defining memory segments
    (base, limit, access rights, flags). In 64-bit long mode, most
    segmentation is bypassed, but GDT is still required for CS/SS/TLS.
    """
    base:        int  = 0
    limit:       int  = 0
    access:      int  = 0
    flags:       int  = 0
    description: str  = ""


@dataclass
class TssDescriptor:
    """SIMULATOR: Task State Segment descriptor.

    The TSS in x86_64 holds RSP0 (kernel stack pointer for ring-0 entry
    from ring-3), interrupt stack table (IST) pointers for NMI/DF etc.,
    and I/O permission bitmap. It is NOT used for task switching in 64-bit mode.
    """
    base:        int  = 0
    limit:       int  = 0
    rsp0:        int  = 0   # Kernel stack pointer loaded on ring-3 -> ring-0 transition
    description: str  = ""


@dataclass
class IdtEntry:
    """SIMULATOR: Interrupt Descriptor Table entry.

    Each IDT entry (gate descriptor) maps an interrupt/exception vector
    to a handler function: offset (handler address), selector (code segment),
    gate type (interrupt gate, trap gate), and DPL (who can software-invoke via INT n).
    """
    offset:      int  = 0
    selector:    int  = 0x08   # Kernel CS
    gate_type:   int  = 0xE    # 64-bit interrupt gate
    dpl:         int  = 0      # Callable from ring 0 only (use 3 for INT 0x80 style)
    vector:      int  = 0
    description: str  = ""


@dataclass
class PageTableEntry:
    """SIMULATOR: A single x86_64 page table entry (PTE).

    Real PTEs are 8-byte integers with bit fields:
    P (present), R/W (writable), U/S (user accessible), NX (no-execute), PFN (page frame number).
    """
    present:         bool = False
    writable:        bool = False
    user_accessible: bool = False
    nx:              bool = False
    pfn:             int  = 0   # Page Frame Number


@dataclass
class PerCpuState:
    """SIMULATOR: Per-CPU kernel state.

    In a real SMP kernel, each CPU has its own data area (per-CPU variables)
    containing the current task pointer, IRQ depth, GS base, etc.
    Accessed via the GS segment register (GS:0 points to per-CPU area).
    """
    cpu_id:       int  = 0
    current_pid:  int  = 0
    current_tid:  int  = 0
    in_interrupt: bool = False
    irq_depth:    int  = 0


class ArchX86_64:
    """SIMULATOR: x86_64 architecture initialization layer.

    Models all the architecture-specific setup that a real kernel performs
    in early boot before any other subsystems are available:
    CPUID detection, GDT/TSS/IDT setup, paging, syscall MSR configuration.

    IMPORTANT: None of these methods execute privileged instructions.
    They simulate the concepts and data structures for educational purposes.
    """

    def __init__(self, logger: KernelLogger):
        self._logger = logger
        self._features: CpuFeatures | None = None
        self._per_cpu: list[PerCpuState] = []

    def detect_cpu_features(self) -> CpuFeatures:
        """SIMULATOR: Detect CPU features via simulated CPUID.

        Real kernel: executes CPUID with leaf 0x1, 0x7, 0x80000001 etc.
        to fill in struct cpuinfo_x86. Results stored per-CPU.
        SIMULATOR: We return a hardcoded 'capable' feature set.
        """
        self._logger.info("ARCH", "SIMULATOR: Executing CPUID to detect CPU features")
        self._logger.info("ARCH", "  Real: CPUID leaf 0x1 -> ECX/EDX feature bits")
        self._logger.info("ARCH", "  Real: CPUID leaf 0x7 -> EBX/ECX extended features (SMEP/SMAP/AVX2)")
        self._logger.info("ARCH", "  Real: CPUID leaf 0x80000001 -> NX bit (EFER.NXE)")
        self._features = CpuFeatures()
        f = self._features
        self._logger.info("ARCH", (
            f"  Detected: NX={f.has_nx} SSE2={f.has_sse2} AVX2={f.has_avx2} "
            f"RDRAND={f.has_rdrand} SMEP={f.has_smep} SMAP={f.has_smap} "
            f"PCID={f.has_pcid} cores={f.cores} threads/core={f.threads_per_core}"
        ))
        return self._features

    def setup_gdt(self) -> List[GdtEntry]:
        """SIMULATOR: Set up the Global Descriptor Table.

        Real kernel: GDT contains null descriptor (entry 0), kernel CS (0x08),
        kernel DS/SS (0x10), user CS32 (0x18), user DS (0x20), user CS64 (0x28),
        TSS descriptor (0x30, 16-byte system descriptor), per-CPU TLS descriptors.
        LGDT instruction loads the GDT register (GDTR) with base+limit.
        SIMULATOR: We construct the data structures without executing LGDT.
        """
        self._logger.info("ARCH", "SIMULATOR: Setting up GDT (Global Descriptor Table)")
        self._logger.info("ARCH", "  Real: would execute LGDT to load GDTR register")
        gdt = [
            GdtEntry(0, 0, 0x00, 0x0, "null descriptor"),
            GdtEntry(0, 0xFFFFF, 0x9A, 0xA, "kernel CS64 (ring-0 code, 64-bit)"),
            GdtEntry(0, 0xFFFFF, 0x92, 0xC, "kernel DS/SS (ring-0 data)"),
            GdtEntry(0, 0xFFFFF, 0xFA, 0xA, "user CS32 (ring-3 compat code)"),
            GdtEntry(0, 0xFFFFF, 0xF2, 0xC, "user DS (ring-3 data)"),
            GdtEntry(0, 0xFFFFF, 0xFA, 0xA, "user CS64 (ring-3 code, 64-bit)"),
        ]
        for i, entry in enumerate(gdt):
            self._logger.debug("ARCH", f"  GDT[{i}]: {entry.description} access=0x{entry.access:02x}")
        self._logger.info("ARCH", f"  GDT initialized with {len(gdt)} entries")
        return gdt

    def setup_tss(self) -> TssDescriptor:
        """SIMULATOR: Set up the Task State Segment.

        Real kernel: Allocates a per-CPU TSS struct, sets RSP0 to the kernel stack
        top for this CPU, installs TSS descriptor in GDT, executes LTR to load
        the Task Register. IST (Interrupt Stack Table) entries are set for NMI/DF.
        SIMULATOR: We just create the data structure.
        """
        self._logger.info("ARCH", "SIMULATOR: Setting up TSS (Task State Segment)")
        self._logger.info("ARCH", "  Real: RSP0 = kernel stack pointer for ring-3 -> ring-0 transitions")
        self._logger.info("ARCH", "  Real: LTR instruction loads Task Register with TSS selector")
        rsp0_sim = 0xFFFF800000010000  # simulated kernel stack top
        tss = TssDescriptor(
            base=0xFFFF800000008000,
            limit=0x67,
            rsp0=rsp0_sim,
            description="CPU0 TSS (ring-0 stack=0xFFFF800000010000)",
        )
        self._logger.info("ARCH", f"  TSS: base=0x{tss.base:016x} RSP0=0x{tss.rsp0:016x}")
        return tss

    def setup_idt(self) -> List[IdtEntry]:
        """SIMULATOR: Set up the Interrupt Descriptor Table.

        Real kernel: 256-entry IDT covering:
          0-31:  CPU exceptions (DE, DB, NMI, BP, OF, BR, UD, NM, DF, TS, NP, SS, GP, PF, MF, AC, MC, XF, VE)
          32-47: Hardware IRQs (remapped from PIC/IOAPIC)
          0x80:  Legacy syscall gate (if used)
          Others: MSI vectors, IPI vectors (0xF0-0xFF range for LAPIC IPIs)
        SIMULATOR: We model a subset for educational value.
        """
        self._logger.info("ARCH", "SIMULATOR: Setting up IDT (Interrupt Descriptor Table)")
        self._logger.info("ARCH", "  Real: 256 entries, each an 16-byte gate descriptor")
        self._logger.info("ARCH", "  Real: LIDT instruction loads IDTR register with base+limit")

        exception_names = [
            "#DE Divide Error", "#DB Debug", "NMI", "#BP Breakpoint",
            "#OF Overflow", "#BR Bound Range", "#UD Invalid Opcode", "#NM No Math",
            "#DF Double Fault", "Reserved", "#TS Invalid TSS", "#NP Segment Not Present",
            "#SS Stack Fault", "#GP General Protection", "#PF Page Fault", "Reserved",
            "#MF x87 FP", "#AC Alignment Check", "#MC Machine Check", "#XF SIMD FP",
        ]
        idt: List[IdtEntry] = []
        for vec in range(256):
            if vec < len(exception_names):
                desc = exception_names[vec]
                dpl = 3 if vec == 3 else 0  # #BP accessible from ring-3 for debuggers
            elif 32 <= vec <= 47:
                desc = f"IRQ{vec - 32}"
                dpl = 0
            elif vec == 0x80:
                desc = "legacy syscall (INT 0x80)"
                dpl = 3
            else:
                desc = f"vector 0x{vec:02x}"
                dpl = 0
            sim_offset = 0xFFFF800000100000 + vec * 0x20
            idt.append(IdtEntry(
                offset=sim_offset, selector=0x08, gate_type=0xE,
                dpl=dpl, vector=vec, description=desc,
            ))

        self._logger.info("ARCH", f"  IDT: {len(idt)} entries installed")
        self._logger.info("ARCH", "  Key vectors: #PF=14 #GP=13 #DF=8 IRQ0=32 syscall=0x80")
        return idt

    def setup_paging(self) -> str:
        """SIMULATOR: Set up x86_64 4-level page tables.

        Real kernel: Allocates physical pages for PML4/PDPT/PD/PT, maps:
          - Kernel at FFFF800000000000 (direct physical map)
          - Kernel text/data at FFFFFFFF80000000 (from linker script)
          - Sets CR3 to PML4 physical address
          - Enables EFER.NXE for NX bit support
          - Sets CR4.SMEP + CR4.SMAP + CR4.PCIDE
        SIMULATOR: No actual page tables created; we just describe the layout.
        """
        self._logger.info("ARCH", "SIMULATOR: Setting up 4-level page tables (PML4)")
        self._logger.info("ARCH", "  Real: PML4 -> PDPT -> PD -> PT, each 512 entries of 8 bytes")
        self._logger.info("ARCH", "  Real: CR3 = physical address of PML4")
        self._logger.info("ARCH", "  Real: EFER.NXE=1 (NX bit in PTEs)")
        self._logger.info("ARCH", "  Real: CR4.SMEP=1, CR4.SMAP=1, CR4.PCIDE=1")
        self._logger.info("ARCH", "  Virtual memory layout (x86_64 canonical):")
        self._logger.info("ARCH", "    0x0000000000000000 - 0x00007FFFFFFFFFFF  user space (128 TB)")
        self._logger.info("ARCH", "    0xFFFF800000000000 - 0xFFFFFFFFFFFFFFFF  kernel space (128 TB)")
        self._logger.info("ARCH", "    0xFFFF800000000000 - 0xFFFFBFFFFFFFFFFF  direct phys map")
        self._logger.info("ARCH", "    0xFFFFFF8000000000 - 0xFFFFFFFFFFFFFFFF  kernel text/data/vmalloc")
        return "paging_initialized_simulated"

    def setup_syscall_entry(self) -> str:
        """SIMULATOR: Configure SYSCALL/SYSRET MSRs for fast system calls.

        Real kernel: Programs three MSRs:
          IA32_STAR (0xC0000081): CS/SS selectors for SYSCALL/SYSRET
          IA32_LSTAR (0xC0000082): 64-bit SYSCALL target RIP (entry_SYSCALL_64)
          IA32_FMASK (0xC0000084): RFLAGS mask - bits to clear on SYSCALL (clears IF)
        SYSCALL is faster than INT 0x80 because it avoids IDT lookup and stack switch
        overhead (uses RSP0 from TSS directly via SYSCALL MSR path).
        SIMULATOR: We just log the concept.
        """
        self._logger.info("ARCH", "SIMULATOR: Configuring SYSCALL/SYSRET MSRs")
        self._logger.info("ARCH", "  Real: WRMSR IA32_STAR -> kernel CS=0x08 user CS=0x2B")
        self._logger.info("ARCH", "  Real: WRMSR IA32_LSTAR -> syscall_entry handler address")
        self._logger.info("ARCH", "  Real: WRMSR IA32_FMASK -> 0x200 (clear IF on entry)")
        self._logger.info("ARCH", "  SYSCALL sets RIP=LSTAR, saves RIP->RCX, RFLAGS->R11")
        self._logger.info("ARCH", "  SYSRET restores RIP<-RCX, RFLAGS<-R11, switches to ring-3")
        return "syscall_msr_configured_simulated"

    def get_cpu_info(self) -> dict:
        """SIMULATOR: Return a summary of CPU information."""
        f = self._features or CpuFeatures()
        return {
            "arch":           "x86_64",
            "cores":          f.cores,
            "threads":        f.cores * f.threads_per_core,
            "features":       {
                "NX":    f.has_nx,
                "SSE2":  f.has_sse2,
                "AVX2":  f.has_avx2,
                "RDRAND": f.has_rdrand,
                "SMEP":  f.has_smep,
                "SMAP":  f.has_smap,
                "PCID":  f.has_pcid,
            },
            "privilege_rings": [r.name for r in PrivilegeRing],
            "kernel_ring":    KERNEL_RING.name,
            "user_ring":      USER_RING.name,
            "long_mode":      True,
            "page_table_levels": 4,
        }
