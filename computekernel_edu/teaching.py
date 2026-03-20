"""
SIMULATOR: Teaching engine for ComputeKERNEL-Edu.
Provides detailed educational explanations of kernel concepts.
"""

from typing import Dict


TOPICS: Dict[str, str] = {
    "scheduler": """\
TOPIC: Preemptive Round-Robin Scheduler
========================================
ComputeKERNEL uses a preemptive round-robin scheduler as its MVP scheduling policy.

HOW IT WORKS IN A REAL KERNEL:
A timer interrupt (from the LAPIC timer or HPET) fires at a configurable frequency
(typically 100, 250, or 1000 Hz on Linux - set by CONFIG_HZ). Each tick, the interrupt
handler calls scheduler_tick() which decrements the current task's time slice counter.
When the time slice reaches zero, the TIF_NEED_RESCHED flag is set in the task's
thread_info flags.

On the return path from the interrupt handler (or any other preemption point), the
kernel checks TIF_NEED_RESCHED. If set, schedule() is called. schedule() calls
the current scheduler class's pick_next_task() to select the next thread, then
calls context_switch() to save the current CPU state and load the new task's state.

Context switching on x86_64 involves:
1. Saving callee-saved registers (rbx, rbp, r12-r15) to the task's kernel stack
2. Switching the stack pointer (RSP) to the new task's kernel stack
3. Updating CR3 if switching to a different address space (TLB flush unless PCID)
4. Loading the new task's FS/GS base (for TLS)
5. Returning to wherever the new task was interrupted

SIMULATOR vs REAL:
In this simulator, tick() is called manually. No real timer fires. Context "switching"
just changes Python attributes. The educational value is in seeing the scheduling
order and understanding the round-robin quantum concept.

KEY TERMS:
- Time slice / quantum: how long a task runs before being preempted
- Run queue: list of RUNNABLE tasks waiting for CPU time
- Context switch: saving/restoring CPU state when switching tasks
- Preemption: forcibly taking CPU from running task (vs cooperative yielding)
- CFS (Completely Fair Scheduler): Linux's default scheduler (not what ComputeKERNEL uses)
""",

    "page_fault": """\
TOPIC: Page Fault Handling (#PF, Interrupt Vector 14)
======================================================
A page fault is one of the most important mechanisms in modern OS memory management.

HOW IT WORKS IN A REAL KERNEL:
When a process accesses a virtual address that is not currently mapped to a physical
page (or violates permissions), the CPU generates a page fault exception (#PF, vector 14).
The hardware automatically pushes an error code and the faulting RIP onto the kernel stack,
then jumps to the IDT handler for vector 14.

The error code bits tell the kernel:
- bit 0 (P): 0=not-present fault, 1=protection violation
- bit 1 (W/R): 0=read, 1=write
- bit 2 (U/S): 0=kernel fault, 1=user-mode fault
- bit 4 (I/D): instruction fetch (NX violation)

The CR2 register holds the faulting virtual address.

The kernel's page fault handler (do_page_fault / exc_page_fault) then:
1. Checks if the fault address is in kernel space (should not happen normally)
2. Looks up the VMA covering the faulting address
3. If no VMA found: SIGSEGV (segmentation fault) to the process
4. If write to read-only VMA: check if copy-on-write is needed
5. If not-present and valid VMA: demand page - allocate a physical page, map it
6. Return from interrupt - the faulting instruction is retried

DEMAND PAGING:
Linux does not physically allocate memory when mmap() is called. Pages are only
allocated when first accessed. This is why a program can "allocate" 1GB but only
use 100MB - the OS only provides pages on demand.

COPY-ON-WRITE (COW):
After fork(), parent and child share the same physical pages marked read-only.
On first write, a page fault fires, the kernel copies the page, remaps it as
writable, and the write proceeds. This makes fork() fast.

SIMULATOR vs REAL:
simulate_page_fault() in memory.py shows what decisions the real handler would make
without actually triggering CPU exceptions or managing physical page tables.
""",

    "vfs_path_walk": """\
TOPIC: VFS Path Resolution (path_walk / namei)
===============================================
When you open a file like "/home/user/doc.txt", the kernel must resolve each
component of the path through the VFS layer.

HOW IT WORKS IN A REAL KERNEL:
Path resolution is performed by the "namei" subsystem (fs/namei.c in Linux).
The entry point is filename_lookup() -> path_lookupat() -> link_path_walk().

For each path component:
1. Start at the root dentry (or CWD dentry for relative paths)
2. Take the RCU read lock (for lock-free dentry lookup)
3. Look up the name in the current directory's dentry cache (dcache)
4. If not in dcache: call inode->i_op->lookup() to ask the filesystem
5. Check execute permission on the directory (X bit)
6. If the component is a symlink: follow it (with loop detection)
7. If a mount point is crossed: look up the mounted filesystem's root

DENTRY CACHE (dcache):
The dentry cache stores recent path lookup results. It's a hash table of
(parent dentry, name) -> dentry mappings. Since filesystem lookups can be
expensive (disk I/O), the dcache provides O(1) cached lookups for hot paths.
The dcache is one of the most heavily used caches in the kernel.

MOUNT POINTS:
When a filesystem is mounted (e.g., ext4 at /home), path resolution detects
when it crosses the mount point and redirects to the mounted filesystem's root.
This is how the single unified namespace "/" works despite multiple filesystems.

PERMISSIONS:
At each step, the kernel checks DAC (discretionary access control) permissions:
execute permission on each directory component, and read/write permission on
the final component based on the open flags.

SIMULATOR vs REAL:
VFS._resolve_path() in vfs.py models the mount-point crossing and directory
traversal, but without dentry caching, symlink following, or permission checks.
""",

    "syscall_dispatch": """\
TOPIC: System Call Dispatch (SYSCALL instruction / entry_SYSCALL_64)
=====================================================================
System calls are the controlled interface between user-space programs and the kernel.

HOW IT WORKS ON x86_64:
Modern x86_64 uses the SYSCALL instruction (not the old INT 0x80).
The kernel programs three MSRs at boot:
  - IA32_LSTAR (0xC0000082): address of the kernel syscall entry point
  - IA32_STAR (0xC0000081): segment selectors for SYSCALL/SYSRET
  - IA32_FMASK (0xC0000084): RFLAGS bits to clear on SYSCALL (clears IF)

When user code executes SYSCALL:
1. RIP is saved to RCX (return address)
2. RFLAGS is saved to R11 (with mask applied)
3. CS/SS are loaded from IA32_STAR
4. RIP jumps to IA32_LSTAR (entry_SYSCALL_64)

In entry_SYSCALL_64 (arch/x86/entry/entry_64.S):
1. Switch from user stack to kernel stack (from TSS.RSP0)
2. Save all user registers (full pt_regs frame)
3. Call do_syscall_64(regs, nr) where nr = rax
4. do_syscall_64 looks up sys_call_table[nr] and calls it
5. Return value goes in rax
6. SYSRET restores RIP from RCX, RFLAGS from R11, switches to ring-3

ARGUMENT PASSING:
Syscall arguments are passed in registers: rdi, rsi, rdx, r10, r8, r9
(Note: r10 instead of rcx, since rcx holds the return address after SYSCALL)

SECURITY:
Before dispatching, the kernel calls syscall_enter_from_user_mode() which:
- Processes pending signals
- Handles ptrace (for debuggers like gdb/strace)
- Runs seccomp filters (sandboxing)

SIMULATOR vs REAL:
SyscallDispatcher.dispatch() in syscall.py models the dispatch table lookup
and handler invocation without any actual ring transitions or register manipulation.
""",

    "copy_from_user": """\
TOPIC: copy_from_user() / copy_to_user() - Safe Kernel/User Data Transfer
==========================================================================
Whenever the kernel needs to read data provided by a user-space program
(e.g., a buffer passed to write(), a struct passed to ioctl()), it MUST
use copy_from_user() rather than directly dereferencing the pointer.

WHY IT'S NECESSARY:
1. ADDRESS VALIDATION: The user pointer could be NULL, unaligned, or point
   into kernel space. access_ok() checks that [addr, addr+size) lies within
   the user address space before any dereference.

2. PAGE FAULT HANDLING: The user page might not be physically present (demand paging).
   copy_from_user() is designed to handle this gracefully using the kernel's
   exception tables (fixup entries in __ex_table).

3. CONCURRENCY: Between access_ok() and the actual copy, another thread could
   unmap the page (TOCTOU). The kernel handles mid-copy faults via fixup entries.

4. SMAP (Supervisor Mode Access Prevention): On modern x86_64, CR4.SMAP=1 means
   the kernel will fault if it directly accesses user memory. copy_from_user()
   temporarily disables SMAP via STAC/CLAC instructions.

HOW FIXUP TABLES WORK:
The assembler generates pairs (faulting_address, fixup_handler) in __ex_table.
If a fault occurs during copy_from_user(), the page fault handler looks up
the faulting address in __ex_table and jumps to the fixup handler, which
returns a partial copy count or -EFAULT to the caller.

COMMON BUG (UAF / Type confusion): If a kernel driver directly dereferences
a user pointer instead of using copy_from_user(), it creates a security
vulnerability (arbitrary read/write from kernel context = full system compromise).

SIMULATOR vs REAL:
This simulator does not implement copy_from_user() because all "user" data is
already Python objects in the same process. The concept is modeled by
validate_user_pointer() in security.py which checks address range validity.
""",

    "device_probing": """\
TOPIC: Device Probing and Driver Binding
=========================================
The Linux device model provides a systematic way for drivers to claim devices.

HOW IT WORKS IN A REAL KERNEL:
1. DEVICE ENUMERATION: A bus driver (PCI, USB, ACPI, platform) enumerates
   connected devices and registers them with device_register(). Each device
   gets a kobject, sysfs entry, and uevent (for udev).

2. DRIVER REGISTRATION: A driver calls pci_register_driver() /
   platform_driver_register() / usb_register() etc., providing:
   - A match table (PCI vendor/device IDs, ACPI HID strings, OF compatible strings)
   - A .probe() callback
   - .remove(), .suspend(), .resume() callbacks

3. BINDING: When a new device appears, the kernel bus iterates all registered
   drivers and calls driver_match_device() for each. If a match is found,
   really_probe() calls driver->probe(device). On success (return 0), the
   device is "claimed" and dev->driver is set.

4. UDEV: The kernel sends a KOBJ_ADD uevent to udevd which creates /dev nodes
   based on rules in /etc/udev/rules.d/.

5. DEFERRED PROBING: If probe() returns -EPROBE_DEFER (dependency not ready),
   the kernel re-tries probing later when more drivers/devices are registered.

SIMULATOR vs REAL:
DeviceRegistry.register() and DriverRegistry.probe_device() in device.py and
driver.py model this matching/binding cycle without PCI config space reads,
interrupt routing, IOMMU mapping, or actual hardware initialization.
""",

    "safe_mode": """\
TOPIC: Safe Mode Boot
======================
Safe mode (or recovery mode) restricts what the kernel loads to allow
recovery from bad driver or module states.

REAL KERNEL ANALOGS:
1. Linux single-user mode: add 'single' or 'init=/bin/sh' to kernel cmdline.
   Only essential filesystems are mounted, no getty/login, root shell.

2. Windows safe mode: loads only essential drivers (VGA, keyboard, disk),
   skips startup programs, uses safe VGA resolution.

3. macOS Safe Mode: skips login items, uses kernel extensions from /System only.

WHAT SAFE MODE DOES IN ComputeKERNEL-EDU:
- modules_enabled=False: no kernel modules can be loaded (no insmod)
- non_essential_drivers=False: only essential drivers (console, timer, disk) load
- serial_log=True: verbose logging to see what goes wrong
- aslr=False: deterministic addressing for debugging
- smap=False: relaxed memory protection for recovery tools

WHEN TO USE:
- A newly loaded kernel module causes a panic/crash
- A driver update breaks boot
- File system corruption requires manual fsck
- Testing kernel changes with minimum driver interference

SIMULATOR IMPLEMENTATION:
SafeMode.check_module_load() and .check_driver_load() gate module/driver
loading based on the active profile. The 'safe_mode' boot profile activates these.
""",

    "simulator_vs_real": """\
TOPIC: This Simulator vs a Real Kernel
========================================
Understanding what this simulator DOES and DOES NOT do is critical.

WHAT THE SIMULATOR MODELS (educationally):
- Boot sequence stages (firmware -> bootloader -> arch init -> mm -> scheduler -> vfs)
- x86_64 architecture concepts (GDT, IDT, TSS, page tables, MSRs, rings)
- Physical memory manager (page frame allocation)
- Virtual memory manager (VMAs, address spaces)
- Process/thread model (task_struct concepts)
- Round-robin preemptive scheduler (ticks, context switches, run queue)
- System call dispatch table (14 syscalls)
- VFS layer (path resolution, mounts, inodes, dentries)
- tmpfs and ext2-inspired filesystems
- Device registry and driver binding
- ELF loader concepts
- IPC: pipes and signals
- Kernel module loader (insmod/rmmod/lsmod)
- Security credentials and capability checks
- Power management states

WHAT THE SIMULATOR DOES NOT DO (and cannot):
- Execute privileged CPU instructions (no LGDT, LIDT, WRMSR, IN/OUT, HLT, STI/CLI)
- Manipulate physical memory or page tables (no CR3 writes)
- Receive real hardware interrupts (no IRQs, no LAPIC, no timer)
- Perform real I/O (no disk reads, no network packets)
- Actually boot on real or virtual hardware
- Run in ring-0 (all Python code runs in user-space)
- Parse real ELF binaries or filesystems

THE REAL ComputeKERNEL:
- Written in C and x86_64 assembly
- Boots on real hardware via GRUB2/Multiboot2
- Implements ring-0 privilege with full hardware control
- Uses actual page tables, interrupts, LAPIC timer, PCI enumeration
- Repository: github.com/ComputerKERNEL/ComputeKERNEL

PURPOSE OF THIS SIMULATOR:
Learn kernel architecture concepts in a safe, inspectable Python environment
without needing to set up a cross-compiler, QEMU, or debug a real kernel crash.
""",

    "pmm": """\
TOPIC: Physical Memory Manager (PMM)
======================================
The PMM is responsible for tracking which physical memory pages are free or in use.

HOW IT WORKS IN A REAL KERNEL:
At boot, the bootloader (GRUB2/Multiboot2/UEFI) provides a memory map describing
physical memory regions as usable, reserved, ACPI reclaimable, etc.

The kernel ingests this map and initializes the PMM:
1. EARLY BOOT: memblock allocator - a simple first-fit allocator used before
   the full PMM is ready. Used to allocate page tables, early kernel data.

2. BUDDY ALLOCATOR: The main PMM in Linux. Physical memory is divided into zones
   (DMA, DMA32, NORMAL, HIGHMEM on 32-bit). Within each zone, the buddy allocator
   manages free pages in orders 0-10 (1, 2, 4, 8, ... 1024 contiguous pages).
   
   - alloc_pages(order): finds the smallest available power-of-2 block, splits it
   - free_pages(page, order): returns pages and merges adjacent buddies

3. ZONES: DMA zone (below 16MB for legacy DMA), DMA32 (below 4GB), NORMAL (rest).
   Some architectures have HIGHMEM for physical memory not directly mapped.

PAGE FRAME NUMBERS (PFN):
Each physical page has a PFN = physical_address / PAGE_SIZE.
The kernel maintains a struct page array (mem_map) with one entry per PFN.
This array can be huge: 1 TB RAM needs ~4GB just for the struct page array.

SIMULATOR vs REAL:
PhysicalMemoryManager uses a flat list of Page objects. It does not implement
buddy splitting/merging, zones, or NUMA awareness. alloc_page() is O(n) not O(log n).
""",

    "vmm": """\
TOPIC: Virtual Memory Manager (VMM)
=====================================
The VMM manages virtual address spaces for all processes and the kernel itself.

HOW IT WORKS IN A REAL KERNEL:
Each process has a memory descriptor (struct mm_struct) containing:
- A red-black tree (mm->mm_rb) and linked list of VMAs (vm_area_struct)
- The PGD (Page Global Directory = PML4) pointer (mm->pgd)
- Statistics: total virtual memory, RSS (resident set size), etc.

VIRTUAL MEMORY AREAS (VMAs):
Each VMA represents a contiguous region with uniform permissions and a backing:
- Anonymous: backed by swap (stack, heap, MAP_ANONYMOUS)
- File-backed: backed by a file via the page cache (text segment, mmap'd files)
- Special: vvar, vdso (kernel-provided user-space pages)

PAGE TABLE HIERARCHY (x86_64 4-level):
  CR3 -> PML4 (512 entries) -> PDPT (512) -> PD (512) -> PT (512 pages)
  Each level covers: 512GB / 1GB / 2MB / 4KB
  
  A virtual address splits into: PML4[9] | PDPT[9] | PD[9] | PT[9] | offset[12]

DEMAND PAGING:
mmap() creates a VMA but does NOT allocate physical pages. Pages are faulted in
on first access. This allows overcommit: allocating more virtual memory than
physical RAM + swap (relying on programs not using all they allocate).

COPY-ON-WRITE:
fork() duplicates the parent's VMAs and marks all pages read-only.
First write to a COW page triggers a fault -> page copy -> remap as writable.

TLB MANAGEMENT:
The TLB (Translation Lookaside Buffer) caches virtual->physical translations.
After unmapping or changing page permissions, the kernel flushes relevant TLB
entries (INVLPG instruction) or all TLBs (full CR3 reload).
With PCID (Process Context IDs), switching address spaces doesn't flush TLB -
each ASID has its own TLB entries.

SIMULATOR vs REAL:
VirtualMemoryManager uses Python dicts. No actual page tables exist.
""",

    "elf_loading": """\
TOPIC: ELF Binary Loading
===========================
When you run a program (execve), the kernel loads the ELF binary into a
new address space.

HOW IT WORKS IN A REAL KERNEL:
1. The execve() syscall calls do_execve() -> search_binary_handler()
2. The kernel reads the first few bytes to identify the binary format
   (ELF magic: 0x7F 'E' 'L' 'F')
3. For ELF: load_elf_binary() in fs/binfmt_elf.c

ELF LOADING STEPS:
a. Read and validate the ELF header (e_ident, e_machine, e_type)
b. Read all program headers (PT_LOAD, PT_DYNAMIC, PT_INTERP, PT_NOTE, etc.)
c. Flush the old address space (exec_mmap())
d. For each PT_LOAD segment:
   - mmap the segment at p_vaddr with appropriate permissions
   - Copy p_filesz bytes from file
   - Zero-fill the remaining p_memsz - p_filesz bytes (BSS)
e. If PT_INTERP present: load the dynamic linker (ld.so) too
f. Set up the initial stack with: argc, argv[], envp[], auxv[]
g. The auxv (auxiliary vector) passes info to ld.so:
   AT_PHDR, AT_PHNUM, AT_ENTRY, AT_RANDOM, AT_HWCAP, etc.
h. If dynamic: set start_thread() to ld.so's entry, not the ELF's e_entry
i. ASLR: randomize load addresses (text, stack, mmap base)

STATIC vs DYNAMIC:
Static ELF: jump directly to e_entry, no dynamic linker needed.
Dynamic ELF: kernel maps both the ELF and ld.so, starts at ld.so's entry,
which loads shared libraries, resolves symbols (PLT/GOT), then calls the ELF entry.

SIMULATOR vs REAL:
FakeElf / ElfLoader models the segment mapping concept without real ELF parsing.
""",

    "module_loading": """\
TOPIC: Kernel Module Loading (LKM - Loadable Kernel Modules)
=============================================================
Kernel modules allow extending the kernel without rebooting.

HOW IT WORKS IN A REAL KERNEL:
1. User runs: insmod module.ko (or modprobe for automatic dependency loading)
2. The finit_module() syscall reads the .ko ELF file
3. load_module() in kernel/module.c:
   a. Allocate kernel memory for the module (vmalloc, module_alloc for text)
   b. Parse the ELF: find .init.text, .text, .data, .bss, __ksymtab, etc.
   c. Relocate the module: patch addresses in the code using relocation entries
      (ELF RELA sections) - update references to kernel symbols like printk
   d. Resolve symbols: look up each undefined symbol in the kernel symbol table
      (System.map / kallsyms). FAIL with -ENOENT if symbol not found.
   e. Verify module signature (if CONFIG_MODULE_SIG=y and key is present)
   f. Run security hooks (LSM: security_kernel_module_request())
   g. Call the module's init() function (marked with module_init())
4. The module is now live in the kernel (MODULE_STATE_LIVE)
5. rmmod: call module's exit() function, then free the module memory

SYMBOL TABLE:
The kernel exports symbols via EXPORT_SYMBOL() / EXPORT_SYMBOL_GPL().
GPL-only symbols cannot be used by non-GPL modules (license checking).
The full symbol table is accessible at /proc/kallsyms.

DEPENDENCIES:
modprobe reads /lib/modules/$(uname -r)/modules.dep to automatically load
dependent modules. If ext4 needs crc32c, modprobe loads crc32c first.

SIMULATOR vs REAL:
ModuleLoader.load() checks dependencies and registers symbols without
any ELF parsing, relocation, or actual code execution.
""",

    "ipc": """\
TOPIC: Inter-Process Communication (IPC)
=========================================
Processes need ways to communicate. The kernel provides several IPC mechanisms.

PIPES:
pipe() creates a unidirectional byte stream between two file descriptors.
The kernel allocates a pipe_inode_info with a 16-page (64KB) ring buffer.
write() to the write-end blocks if the buffer is full (pipe is full).
read() from the read-end blocks if the buffer is empty.
When the write-end is closed, read() returns 0 (EOF).
When the read-end is closed, write() returns -EPIPE and SIGPIPE is sent.

SIGNALS:
Signals are asynchronous notifications to processes. Common signals:
- SIGTERM (15): polite termination request (can be caught, handled, ignored)
- SIGKILL (9): forceful kill (CANNOT be caught or ignored - always works)
- SIGSEGV (11): segmentation fault (usually from bad memory access)
- SIGCHLD (17): child process state change (enables non-blocking wait)
- SIGINT (2): keyboard interrupt (Ctrl+C sends this to foreground process group)
- SIGSTOP (19): stop process (like SIGKILL, cannot be caught or ignored)

Signal delivery: When a signal is sent, it's added to the target task's
pending signal set (task->pending). On the return from interrupt/syscall,
the kernel checks TIF_SIGPENDING and calls do_signal() which invokes the
registered signal handler (or default action: terminate, core dump, stop, ignore).

REAL-TIME SIGNALS: Signals 34-64 are queued (multiple can be pending).
Standard signals 1-31 are not queued (duplicate sends are coalesced).

OTHER IPC MECHANISMS (not simulated here):
- Shared memory (mmap MAP_SHARED, POSIX shm, SysV shm)
- Message queues (POSIX mq_*, SysV msgget/msgsnd/msgrcv)
- Semaphores (POSIX sem_*, SysV semget/semop)
- Sockets (Unix domain sockets for same-host IPC)
- futex (fast userspace mutex - used by pthreads)
""",

    "boot_flow": """\
TOPIC: Kernel Boot Flow
========================
How a kernel goes from power-on to running init.

STAGE 1: FIRMWARE (BIOS/UEFI)
Power-on triggers CPU reset vector (0xFFFFFFF0 on x86). BIOS/UEFI POST:
memory test, hardware enumeration (PCI, ACPI tables), selects boot device.
UEFI provides boot services and runtime services, passes control to the bootloader.

STAGE 2: BOOTLOADER (GRUB2)
GRUB2 reads its config (/boot/grub/grub.cfg), finds the kernel image (vmlinuz)
and initramfs (initrd.img), loads them into memory.
Passes a Multiboot2 information structure to the kernel with: memory map, framebuffer
info, ACPI RSDP pointer, kernel command line.
Jumps to the kernel's 32-bit entry point (with protected mode already active).

STAGE 3: ARCH EARLY INIT (startup_64 in Linux)
Assembly code: set up initial page tables (map kernel at high half), enable long mode
(set EFER.LME, CR0.PG), jump to 64-bit code. Then call start_kernel().

STAGE 4: start_kernel() [MAIN KERNEL INIT]
setup_arch(): parse memory map, set up GDT/IDT/TSS, CPUID features, APIC
mm_init(): initialize memory zones, buddy allocator, slab allocator, vmalloc
sched_init(): create per-CPU run queues, init idle tasks
vfs_caches_init(): dcache, icache, mount hashtable
rest_init(): spawn kernel_init thread (PID 1) and kthreadd (PID 2)

STAGE 5: kernel_init (PID 1)
Load essential kernel modules, mount root filesystem, run /sbin/init (or systemd).
This is the transition from kernel-space to user-space init.

STAGE 6: init / systemd
Reads /etc/inittab or systemd units, starts services, gettys, etc.
The kernel's job is done - it just handles interrupts, syscalls, scheduling.

SIMULATOR vs REAL:
BootPipeline simulates all these stages as Python method calls.
No real hardware initialization, no real bootloader, no real page table setup.
""",
}


class TeachingEngine:
    """SIMULATOR: Educational teaching engine for ComputeKERNEL-Edu.

    Provides detailed explanations of kernel concepts, connecting what
    this simulator does to how a real kernel works.
    """

    def explain(self, topic: str) -> str:
        """SIMULATOR: Return a detailed explanation for the given topic."""
        text = TOPICS.get(topic.lower())
        if text is None:
            available = ", ".join(sorted(TOPICS.keys()))
            return (
                f"Unknown topic: '{topic}'\n"
                f"Available topics: {available}"
            )
        return text.strip()

    def list_topics(self) -> list:
        """SIMULATOR: Return list of available topics."""
        return sorted(TOPICS.keys())

    def search(self, keyword: str) -> list:
        """SIMULATOR: Find topics that mention a keyword."""
        kw = keyword.lower()
        return [
            topic for topic, text in TOPICS.items()
            if kw in text.lower() or kw in topic.lower()
        ]
