"""
SIMULATOR: Security and credentials subsystem.
Models process credentials, capability checks, and access control.

Real kernel: Security is enforced via the LSM (Linux Security Module) framework.
The kernel checks permissions at syscall boundaries using the credentials of the
calling process (task_cred()). Capabilities replace traditional superuser checks.

SIMULATOR: We model the basic credential/permission concepts for education.
"""

from typing import Optional
from .process import Credentials
from .logger import KernelLogger


# Capability constants (subset of Linux capabilities)
CAP_CHOWN       = 0   # make arbitrary changes to file ownership
CAP_DAC_OVERRIDE = 1  # bypass file read/write/execute permission checks
CAP_SETUID      = 7   # set UID of a process
CAP_NET_ADMIN   = 12  # perform network administration tasks
CAP_SYS_ADMIN   = 21  # wide-ranging system administration capability
CAP_SYS_MODULE  = 16  # load/unload kernel modules
CAP_SYS_BOOT    = 22  # reboot the system
CAP_SYS_RAWIO   = 17  # raw I/O access


def check_permission(creds: Credentials, capability: int) -> bool:
    """SIMULATOR: Check if credentials grant the given capability.

    Real kernel: capable() checks the current task's effective capability set.
    In Linux, root (euid=0) has all capabilities unless the capability bounding
    set has restricted them. Non-root processes have only their permitted set.
    SIMULATOR: We grant all capabilities to root (euid=0) and none to others.
    """
    if creds.euid == 0:
        return True
    # Non-root: no capabilities in this simplified model
    return False


def validate_user_pointer(addr: int, size: int, pid: int) -> bool:
    """SIMULATOR: Validate that a user-space pointer is within user address space.

    Real kernel: access_ok() checks that the address range [addr, addr+size)
    falls within the user address space (< USER_DS). This prevents user programs
    from passing kernel addresses to copy_from_user()/copy_to_user() to leak
    or corrupt kernel memory.
    SIMULATOR: We check against the canonical x86_64 user address space limit.
    """
    USER_MAX = 0x00007FFFFFFFFFFF
    if addr <= 0 or size <= 0:
        return False
    if addr + size > USER_MAX:
        return False
    return True


class CredentialManager:
    """SIMULATOR: Manages process credentials and permission checks.

    Real kernel: The credential system (cred.c) manages the lifetime of
    struct cred objects. Credentials are copy-on-write: a process gets a
    fresh copy when it needs to modify its credentials (e.g., setuid, execve
    with setuid binary). The LSM hooks intercept all security-sensitive operations.
    """

    def create_creds(self, uid: int = 0, gid: int = 0) -> Credentials:
        """SIMULATOR: Create a new credentials object.

        Real kernel: prepare_creds() / commit_creds() manages the credential
        lifecycle with reference counting (struct cred.usage).
        """
        return Credentials(uid=uid, gid=gid, euid=uid, egid=gid)

    def check_vfs_open(self, creds: Credentials, path: str, write: bool = False) -> bool:
        """SIMULATOR: Check VFS open permission.

        Real kernel: inode_permission() calls security_inode_permission() which
        invokes the LSM hook. The DAC (discretionary access control) check
        compares inode uid/gid/mode against the process's euid/egid.
        SIMULATOR: Root can open anything; others can only open non-/proc paths.
        """
        if creds.is_root:
            return True
        # Non-root cannot open /proc/kcore or /dev/mem (simplified)
        restricted = ["/proc/kcore", "/dev/mem", "/dev/port"]
        if path in restricted:
            return False
        return True

    def check_syscall(self, creds: Credentials, syscall_name: str) -> bool:
        """SIMULATOR: Check if credentials permit a privileged syscall.

        Real kernel: Some syscalls (reboot, init_module, kexec_load, etc.)
        require CAP_SYS_BOOT, CAP_SYS_MODULE, CAP_SYS_ADMIN etc.
        SIMULATOR: We restrict module loading and reboot to root.
        """
        privileged_syscalls = {"init_module", "delete_module", "reboot", "kexec_load"}
        if syscall_name in privileged_syscalls:
            return check_permission(creds, CAP_SYS_ADMIN)
        return True

    def drop_privileges(self, creds: Credentials, new_uid: int) -> Credentials:
        """SIMULATOR: Drop privileges by changing effective UID.

        Real kernel: setuid() syscall changes the process credentials.
        Once a process drops from root to non-root, it generally cannot
        regain root privileges (unless it has CAP_SETUID).
        """
        return Credentials(
            uid=new_uid, gid=creds.gid,
            euid=new_uid, egid=creds.egid,
        )
