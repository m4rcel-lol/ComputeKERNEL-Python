"""
SIMULATOR: Interactive shell for ComputeKERNEL-Edu.
Provides a REPL interface to inspect and interact with the simulated kernel.
"""

import sys
import cmd

from .kernel import KernelState, kmain
from .profiles import PROFILES, DEBUG_PROFILE
from .roadmap import format_roadmap
from .utils import (
    size_fmt, hex_addr, table,
    green, red, yellow, cyan, bold, dim,
)


BANNER = """
╔══════════════════════════════════════════════════════════════════╗
║          ComputeKERNEL-Edu  v0.1.0  (Educational Simulator)      ║
║                                                                  ║
║  DISCLAIMER: This is a Python userspace simulator.              ║
║  It does NOT run on hardware or execute privileged instructions. ║
║  Type 'help' for commands, 'teach <topic>' to learn kernel       ║
║  concepts, 'topics' to list all available educational topics.   ║
╚══════════════════════════════════════════════════════════════════╝
"""


class KernelShell(cmd.Cmd):
    """SIMULATOR: Interactive shell for exploring the simulated kernel."""

    intro  = BANNER
    prompt = cyan("kernel> ")

    def __init__(self, kernel: KernelState):
        """SIMULATOR: Create the shell with a reference to the kernel state."""
        super().__init__()
        self.kernel = kernel

    # -------------------------------------------------------------------------
    # Boot commands
    # -------------------------------------------------------------------------

    def do_boot(self, arg):
        """Boot the simulated kernel. Usage: boot [profile]
Profiles: debug (default), release, safe_mode"""
        args = arg.strip().split()
        profile_name = args[0] if args else "debug"
        profile = PROFILES.get(profile_name, DEBUG_PROFILE)

        if self.kernel.booted:
            print(yellow("Kernel already booted. Use 'reboot' to restart."))
            return

        print(bold(f"\n[BOOT] Starting boot sequence with profile '{profile_name}'..."))
        self.kernel.init(profile)
        ok = self.kernel.boot()
        if ok:
            print(green("\n[BOOT] Boot complete!"))
        else:
            print(red("\n[BOOT] Boot FAILED!"))

    def do_reboot(self, arg):
        """Reboot the simulated kernel. Usage: reboot [profile]"""
        args = arg.strip().split()
        profile_name = args[0] if args else self.kernel.profile.name
        profile = PROFILES.get(profile_name, DEBUG_PROFILE)

        if self.kernel.power:
            self.kernel.power.reboot()
        print(yellow("Simulating reboot..."))
        # Reset state
        self.kernel.__init__()
        self.kernel.init(profile)
        self.kernel.boot()
        print(green("Reboot complete."))

    def do_step(self, arg):
        """Step through the boot sequence one stage at a time."""
        if not self.kernel._init_complete:
            print("Run 'boot' first, or use 'boot' which runs all stages.")
            return
        result = self.kernel.boot_step()
        if result is None:
            print(green("All boot stages complete."))
        elif result.success:
            print(green(f"[OK] {result.stage.name}: {result.message} ({result.duration_ms:.1f}ms)"))
        else:
            print(red(f"[FAIL] {result.stage.name}: {result.message}"))

    # -------------------------------------------------------------------------
    # Status/info commands
    # -------------------------------------------------------------------------

    def do_status(self, arg):
        """Show kernel status summary."""
        if not self.kernel._init_complete:
            print("Kernel not initialized. Run 'boot' first.")
            return
        s = self.kernel.status()
        rows = [(k, str(v)) for k, v in s.items()]
        print(table(["Key", "Value"], rows))

    def do_ps(self, arg):
        """List processes. Usage: ps"""
        pt = self.kernel.process_table
        if not pt:
            print("Process table not initialized.")
            return
        procs = pt.all()
        if not procs:
            print("No processes.")
            return
        rows = [
            (p.pid, p.ppid, p.name, p.state.name,
             p.creds.uid, p.cmdline or "")
            for p in procs
        ]
        print(table(["PID", "PPID", "NAME", "STATE", "UID", "CMDLINE"], rows))

    def do_threads(self, arg):
        """List threads. Usage: threads"""
        tt = self.kernel.thread_table
        if not tt:
            print("Thread table not initialized.")
            return
        threads = tt.all()
        if not threads:
            print("No threads.")
            return
        rows = [
            (t.tid, t.pid, t.name, t.state.name,
             "K" if t.is_kernel_thread else "U",
             t.remaining_ticks)
            for t in threads
        ]
        print(table(["TID", "PID", "NAME", "STATE", "TYPE", "TICKS"], rows))

    def do_sched(self, arg):
        """Show scheduler status."""
        sched = self.kernel.scheduler
        if not sched:
            print("Scheduler not initialized.")
            return
        s = sched.status()
        print(f"  Tick count:       {s['tick_count']}")
        print(f"  Context switches: {s['context_switches']}")
        print(f"  Current thread:   {s['current_thread']}")
        print(f"  Runqueue length:  {s['runqueue_length']}")
        if s['runqueue']:
            print(f"  Runqueue:         {', '.join(s['runqueue'])}")
        if s['blocked']:
            print(f"  Blocked:          {', '.join(s['blocked'])}")

    def do_tick(self, arg):
        """Advance the scheduler by N ticks. Usage: tick [N]"""
        sched = self.kernel.scheduler
        if not sched:
            print("Scheduler not initialized.")
            return
        try:
            n = int(arg.strip()) if arg.strip() else 1
        except ValueError:
            print("Usage: tick [N]")
            return
        sched.tick_n(n)
        s = sched.status()
        print(f"Advanced {n} tick(s). Total ticks: {s['tick_count']}")
        print(f"  Current: {s['current_thread']}")

    def do_mem(self, arg):
        """Show memory statistics."""
        if not self.kernel.pmm:
            print("Memory manager not initialized.")
            return
        pmm_stats = self.kernel.pmm.stats()
        kmalloc_stats = self.kernel.kmalloc.usage() if self.kernel.kmalloc else {}
        print(bold("Physical Memory:"))
        print(f"  Total pages:   {pmm_stats['total_pages']}")
        print(f"  Free pages:    {pmm_stats['free_pages']}")
        print(f"  Used pages:    {pmm_stats['used_pages']}")
        print(f"  Total:         {size_fmt(pmm_stats['total_bytes'])}")
        print(f"  Free:          {size_fmt(pmm_stats['free_bytes'])}")
        if kmalloc_stats:
            print(bold("Kernel Allocator (kmalloc):"))
            print(f"  Allocations:   {kmalloc_stats['allocations']}")
            print(f"  Bytes:         {size_fmt(kmalloc_stats['bytes_allocated'])}")
            print(f"  Next addr:     {kmalloc_stats['next_addr']}")

    def do_vmm(self, arg):
        """Show virtual memory maps. Usage: vmm [pid]"""
        vmm = self.kernel.vmm
        if not vmm:
            print("VMM not initialized.")
            return
        if arg.strip():
            try:
                pid = int(arg.strip())
                pids = [pid]
            except ValueError:
                print("Usage: vmm [pid]")
                return
        else:
            pids = list(vmm.address_spaces.keys())

        for pid in pids:
            as_ = vmm.address_spaces.get(pid)
            if as_ is None:
                print(f"No address space for pid={pid}")
                continue
            print(bold(f"\nPID {pid} address space:"))
            rows = [
                (hex_addr(vma.start), hex_addr(vma.end),
                 vma.flags, size_fmt(vma.size), vma.name)
                for vma in as_.areas
            ]
            if rows:
                print(table(["START", "END", "FLAGS", "SIZE", "NAME"], rows))
            else:
                print("  (empty)")

    def do_pagefault(self, arg):
        """Simulate a page fault. Usage: pagefault <pid> <addr_hex> [write]"""
        args = arg.strip().split()
        if len(args) < 2:
            print("Usage: pagefault <pid> <addr_hex> [write]")
            return
        vmm = self.kernel.vmm
        if not vmm:
            print("VMM not initialized.")
            return
        try:
            pid  = int(args[0])
            addr = int(args[1], 16)
            write = len(args) > 2 and args[2].lower() in ("write", "w", "1", "true")
        except ValueError:
            print("Usage: pagefault <pid> <addr_hex> [write]")
            return
        result = vmm.simulate_page_fault(pid, addr, write)
        print(result)

    def do_dmesg(self, arg):
        """Show kernel log (dmesg). Usage: dmesg [level]
Levels: debug, info, warn, error, panic"""
        from .logger import LogLevel
        level_map = {
            "debug": LogLevel.DEBUG,
            "info":  LogLevel.INFO,
            "warn":  LogLevel.WARN,
            "error": LogLevel.ERROR,
            "panic": LogLevel.PANIC,
        }
        level = level_map.get(arg.strip().lower(), LogLevel.DEBUG)
        output = self.kernel.logger.dump(level)
        if output:
            print(output)
        else:
            print("(no log entries)")

    def do_lsdev(self, arg):
        """List registered devices. Usage: lsdev"""
        dev_reg = self.kernel.device_registry
        if not dev_reg:
            print("Device registry not initialized.")
            return
        devices = dev_reg.list_all()
        if not devices:
            print("No devices.")
            return
        rows = [
            (d.name, d.device_class.name, d.major, d.minor,
             d.bound_driver or "(none)", d.description)
            for d in devices
        ]
        print(table(["NAME", "CLASS", "MAJOR", "MINOR", "DRIVER", "DESCRIPTION"], rows))

    def do_lsdrv(self, arg):
        """List registered drivers. Usage: lsdrv"""
        drv_reg = self.kernel.driver_registry
        if not drv_reg:
            print("Driver registry not initialized.")
            return
        drivers = drv_reg.list_all()
        if not drivers:
            print("No drivers.")
            return
        rows = [
            (d.name, "loaded" if d.is_loaded else "unloaded",
             ", ".join(d.bound_devices) or "(none)",
             d.description)
            for d in drivers
        ]
        print(table(["NAME", "STATE", "BOUND DEVICES", "DESCRIPTION"], rows))

    def do_lsmod(self, arg):
        """List kernel modules. Usage: lsmod"""
        ml = self.kernel.module_loader
        if not ml:
            print("Module loader not initialized.")
            return
        loaded = ml.list_loaded()
        available = ml.list_available()
        print(f"Loaded modules ({len(loaded)} / {len(available)} available):")
        rows = [
            (m.name, m.version, "LOADED" if m.is_loaded else "available",
             ", ".join(m.dependencies) or "(none)", m.description)
            for m in available
        ]
        print(table(["NAME", "VERSION", "STATE", "DEPS", "DESCRIPTION"], rows))

    def do_insmod(self, arg):
        """Load a kernel module. Usage: insmod <name>"""
        name = arg.strip()
        if not name:
            print("Usage: insmod <name>")
            return
        ml = self.kernel.module_loader
        if not ml:
            print("Module loader not initialized.")
            return
        ok = ml.load(name)
        if ok:
            print(green(f"Module '{name}' loaded."))
        else:
            print(red(f"Failed to load module '{name}'."))

    def do_rmmod(self, arg):
        """Unload a kernel module. Usage: rmmod <name>"""
        name = arg.strip()
        if not name:
            print("Usage: rmmod <name>")
            return
        ml = self.kernel.module_loader
        if not ml:
            print("Module loader not initialized.")
            return
        ok = ml.unload(name)
        if ok:
            print(green(f"Module '{name}' unloaded."))
        else:
            print(red(f"Failed to unload module '{name}'."))

    def do_vfs(self, arg):
        """VFS operations. Usage: vfs ls <path> | vfs cat <path> | vfs mounts"""
        args = arg.strip().split(None, 1)
        if not args:
            print("Usage: vfs ls <path> | vfs cat <path> | vfs mounts")
            return
        vfs = self.kernel.vfs
        if not vfs:
            print("VFS not initialized.")
            return

        cmd_name = args[0]
        path = args[1].strip() if len(args) > 1 else "/"

        if cmd_name == "mounts":
            mounts = vfs.list_mounts()
            rows = [(mp.mountpoint, mp.fs.fstype, mp.source) for mp in mounts]
            print(table(["TARGET", "FSTYPE", "SOURCE"], rows))

        elif cmd_name == "ls":
            entries = vfs.readdir(path)
            if entries is None:
                print(f"ls: cannot access '{path}': No such file or directory")
                return
            for name, ino in entries:
                print(f"  {name:30s} (ino={ino})")

        elif cmd_name == "cat":
            data = vfs.read_path(path, 4096)
            if data is None:
                print(f"cat: {path}: No such file or directory")
            else:
                print(data.decode("utf-8", errors="replace"), end="")

        elif cmd_name == "mkdir":
            ok = vfs.mkdir(path)
            if ok:
                print(green(f"mkdir: created '{path}'"))
            else:
                print(red(f"mkdir: cannot create '{path}'"))

        elif cmd_name == "write":
            parts = path.split(" ", 1)
            if len(parts) < 2:
                print("Usage: vfs write <path> <data>")
                return
            fpath, content = parts
            ok = vfs.write_path(fpath, content.encode())
            if ok is not False:
                print(green(f"Wrote {len(content)} bytes to '{fpath}'"))
            else:
                print(red(f"write: failed for '{fpath}'"))
        else:
            print("Usage: vfs ls <path> | vfs cat <path> | vfs mounts | vfs mkdir <path>")

    def do_syscall(self, arg):
        """Simulate a syscall. Usage: syscall <pid> <nr> [args...]
Common NRs: 0=read 1=write 2=openat 3=close 39=getpid 57=fork 60=exit 62=kill"""
        from .syscall import SyscallDispatcher
        args = arg.strip().split()
        if len(args) < 2:
            print("Usage: syscall <pid> <nr> [args...]")
            return
        try:
            pid = int(args[0])
            nr  = int(args[1])
        except ValueError:
            print("pid and nr must be integers")
            return

        if not self.kernel.process_table:
            print("Process table not initialized.")
            return

        dispatcher = SyscallDispatcher(
            process_table=self.kernel.process_table,
            thread_table=self.kernel.thread_table,
            vfs=self.kernel.vfs,
            vmm=self.kernel.vmm,
            logger=self.kernel.logger,
        )
        extra = args[2:]
        result = dispatcher.dispatch(pid, nr, *extra)
        color = green if result >= 0 else red
        print(color(f"syscall(pid={pid}, nr={nr}) = {result}"))

    def do_signal(self, arg):
        """Send a signal to a process. Usage: signal <pid> <signame>
Signals: SIGTERM SIGKILL SIGINT SIGHUP SIGUSR1 SIGUSR2 SIGCHLD SIGSEGV SIGSTOP"""
        from .ipc import Signal
        args = arg.strip().split()
        if len(args) < 2:
            print("Usage: signal <pid> <signame>")
            return
        ipc = self.kernel.ipc
        if not ipc:
            print("IPC not initialized.")
            return
        try:
            pid = int(args[0])
        except ValueError:
            print("pid must be an integer")
            return
        sig_name = args[1].upper()
        if not sig_name.startswith("SIG"):
            sig_name = "SIG" + sig_name
        try:
            sig = Signal[sig_name]
        except KeyError:
            print(f"Unknown signal: {args[1]}")
            return
        ok = ipc.send_signal(pid, sig)
        if ok:
            print(green(f"Signal {sig.name} sent to pid={pid}"))
        else:
            print(red(f"Failed to send signal to pid={pid}"))

    def do_power(self, arg):
        """Power management. Usage: power <shutdown|suspend|resume|reboot|status>"""
        pm = self.kernel.power
        if not pm:
            print("Power manager not initialized.")
            return
        cmd_name = arg.strip().lower()
        if cmd_name == "shutdown":
            pm.shutdown()
            print(yellow("System shutting down (simulated). Type 'reboot' to restart."))
        elif cmd_name == "suspend":
            pm.suspend()
            print(yellow("System suspended (S3). Type 'power resume' to wake."))
        elif cmd_name == "resume":
            pm.resume()
            print(green("System resumed."))
        elif cmd_name == "reboot":
            self.do_reboot("")
        elif cmd_name == "status":
            s = pm.status()
            print(f"  Power state: {s['current_state']} ({s['state_name']})")
            print(f"  Transitions: {s['transitions']}")
        else:
            print("Usage: power <shutdown|suspend|resume|reboot|status>")

    def do_safemode(self, arg):
        """Show safe mode status."""
        sm = self.kernel.safe_mode
        if not sm:
            print("Safe mode not initialized.")
            return
        r = sm.report()
        rows = [(k, str(v)) for k, v in r.items()]
        print(table(["Setting", "Value"], rows))

    def do_arch(self, arg):
        """Show CPU/arch information."""
        arch = self.kernel.arch
        if not arch:
            print("Arch layer not initialized.")
            return
        info = arch.get_cpu_info()
        rows = [(k, str(v)) for k, v in info.items()]
        print(table(["Property", "Value"], rows))

    def do_ext2(self, arg):
        """Show ext2 superblock info (if ext2 module is loaded)."""
        ml = self.kernel.module_loader
        if ml and not any(m.name == "ext2" and m.is_loaded for m in ml.list_loaded()):
            print(yellow("ext2 module not loaded. Run 'insmod ext2' first."))
            print("Showing ext2 concept anyway (educational simulator):")

        from .fs_ext2 import Ext2FS
        ext2 = Ext2FS(self.kernel.logger, volume_name="edu-vol")
        info = ext2.superblock_info()
        rows = [(k, str(v)) for k, v in info.items()]
        print(bold("Ext2 Superblock Info (simulated volume):"))
        print(table(["Field", "Value"], rows))

    def do_elf(self, arg):
        """Demonstrate ELF loading. Usage: elf [name]"""
        from .elfloader import FakeElf, ElfLoader
        name = arg.strip() or "hello"
        elf = FakeElf.make_simple(name)
        print(bold(f"ELF binary: '{elf.name}' (simulated)"))
        print(f"  Architecture: {elf.arch}")
        print(f"  Entry point:  0x{elf.entry_point:016x}")
        print(f"  Interpreter:  {elf.interpreter}")
        print()
        rows = [
            (s.seg_type, hex_addr(s.vaddr), size_fmt(s.size), s.flags, s.name)
            for s in elf.segments
        ]
        print(table(["TYPE", "VADDR", "SIZE", "FLAGS", "NAME"], rows))

        if self.kernel.vmm and self.kernel.process_table:
            procs = self.kernel.process_table.all()
            if procs:
                pid = procs[-1].pid
                loader = ElfLoader(self.kernel.vmm, self.kernel.logger)
                entry = loader.load(elf, pid)
                if entry > 0:
                    print(green(f"\nELF loaded for pid={pid}, entry=0x{entry:016x}"))

    def do_pipe(self, arg):
        """Demonstrate pipe IPC. Usage: pipe"""
        ipc = self.kernel.ipc
        if not ipc:
            print("IPC not initialized.")
            return
        pipe = ipc.create_pipe()
        print(f"Pipe created: read_fd={pipe.read_fd} write_fd={pipe.write_fd}")
        msg = b"Hello from the write end of the pipe!\n"
        n = pipe.write(msg)
        print(f"Wrote {n} bytes to pipe")
        data = pipe.read(n)
        print(f"Read from pipe: {data.decode()}", end="")
        print(f"Pipe buffer available: {pipe.available} bytes")

    def do_roadmap(self, arg):
        """Show the ComputeKERNEL feature roadmap."""
        print(format_roadmap())

    def do_netinfo(self, arg):
        """Show networking status (not yet implemented)."""
        print(yellow("""
ComputeKERNEL Networking Status
================================
Networking (TCP/IP stack, NIC drivers, SSH daemon) is NOT yet implemented
in either the real ComputeKERNEL C kernel or this Python simulator.

This is on the roadmap. Run 'roadmap' to see planned features.

What IS planned:
  - TCP/IP stack (lwIP-based or custom)
  - Network device driver framework (virtio-net, e1000)
  - SSH daemon (in-kernel)
  - Socket API (socket, bind, listen, accept, connect, send, recv)
"""))

    # -------------------------------------------------------------------------
    # Teaching commands
    # -------------------------------------------------------------------------

    def do_teach(self, arg):
        """Get a detailed educational explanation. Usage: teach <topic>"""
        topic = arg.strip()
        if not topic:
            print("Usage: teach <topic>")
            print("Run 'topics' to see available topics.")
            return
        print(self.kernel.teach.explain(topic))

    def do_topics(self, arg):
        """List all available teaching topics."""
        topics = self.kernel.teach.list_topics()
        print(bold("Available teaching topics:"))
        for i, t in enumerate(topics, 1):
            print(f"  {i:2d}. {t}")
        print(f"\nUse: teach <topic>")

    def do_search(self, arg):
        """Search teaching topics by keyword. Usage: search <keyword>"""
        kw = arg.strip()
        if not kw:
            print("Usage: search <keyword>")
            return
        results = self.kernel.teach.search(kw)
        if results:
            print(f"Topics matching '{kw}':")
            for t in results:
                print(f"  - {t}")
        else:
            print(f"No topics found for '{kw}'")

    def do_disclaimer(self, arg):
        """Show the educational disclaimer."""
        from . import __disclaimer__
        print(bold("\n" + "=" * 70))
        print(bold("IMPORTANT DISCLAIMER"))
        print("=" * 70)
        print(__disclaimer__)
        print()
        print("This simulator is for EDUCATIONAL PURPOSES ONLY.")
        print("It runs entirely in Python userspace.")
        print("No privileged CPU instructions are executed.")
        print("No hardware is accessed or modified.")
        print("=" * 70 + "\n")

    # -------------------------------------------------------------------------
    # Shell utilities
    # -------------------------------------------------------------------------

    def do_profile(self, arg):
        """Show or switch boot profiles. Usage: profile [debug|release|safe_mode]"""
        if arg.strip():
            name = arg.strip()
            if name not in PROFILES:
                print(f"Unknown profile '{name}'. Available: {', '.join(PROFILES.keys())}")
                return
            print(yellow(f"Note: profile change takes effect on next boot."))
            print(f"Use: reboot {name}")
        else:
            p = self.kernel.profile
            print(f"Current profile: {bold(p.name)}")
            print(f"Description: {p.description}")
            rows = [
                ("serial_log",            str(p.serial_log)),
                ("modules_enabled",       str(p.modules_enabled)),
                ("non_essential_drivers", str(p.non_essential_drivers)),
                ("debug_symbols",         str(p.debug_symbols)),
                ("kmalloc_debug",         str(p.kmalloc_debug)),
                ("scheduler_debug",       str(p.scheduler_debug)),
                ("aslr",                  str(p.aslr)),
                ("nx_enforcement",        str(p.nx_enforcement)),
                ("smep",                  str(p.smep)),
                ("smap",                  str(p.smap)),
            ]
            print(table(["Setting", "Value"], rows))

    def do_clear(self, arg):
        """Clear the screen."""
        import os
        os.system("clear" if os.name == "posix" else "cls")

    def do_exit(self, arg):
        """Exit the simulator."""
        print(dim("Shutting down ComputeKERNEL-Edu simulator..."))
        return True

    def do_quit(self, arg):
        """Exit the simulator."""
        return self.do_exit(arg)

    def do_EOF(self, arg):
        """Handle Ctrl+D."""
        print()
        return self.do_exit(arg)

    def emptyline(self):
        """Do nothing on empty input."""
        pass

    def default(self, line):
        """Handle unknown commands."""
        print(red(f"Unknown command: '{line.split()[0]}'  (type 'help' for commands)"))


def main():
    """SIMULATOR: Entry point for the computekernel-edu CLI."""
    args = sys.argv[1:]
    profile_name = "debug"
    quiet = False

    for a in args:
        if a in PROFILES:
            profile_name = a
        elif a in ("--quiet", "-q"):
            quiet = True
        elif a in ("--help", "-h"):
            print("ComputeKERNEL-Edu - Educational kernel simulator")
            print("Usage: computekernel-edu [profile] [--quiet]")
            print("Profiles:", ", ".join(PROFILES.keys()))
            sys.exit(0)

    # Create kernel with logging disabled for shell startup
    profile = PROFILES.get(profile_name, DEBUG_PROFILE)

    # Temporarily suppress output during init unless verbose requested
    if quiet:
        profile.serial_log = False

    kernel = KernelState()
    kernel.logger._serial_sink = False  # suppress log spam during boot
    kernel.init(profile)

    # Re-enable logging for boot if not quiet
    if not quiet:
        kernel.logger._serial_sink = True

    kernel.boot()
    kernel.logger._serial_sink = False  # suppress log spam during shell use

    shell = KernelShell(kernel)
    try:
        shell.cmdloop()
    except KeyboardInterrupt:
        print("\nInterrupted.")


if __name__ == "__main__":
    main()
