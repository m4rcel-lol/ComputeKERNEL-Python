"""
SIMULATOR: Virtual Filesystem Switch (VFS) layer.
Models the Linux VFS abstraction that allows multiple filesystem types
to coexist under a unified interface.

Real kernel: The VFS defines abstract inode/dentry/file/super_block structures
and a set of operations (inode_operations, file_operations, super_operations).
Each filesystem driver implements these operations for its specific on-disk format.

SIMULATOR: We use Python classes/dicts to model these concepts without
any actual disk I/O or filesystem parsing.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple
from .logger import KernelLogger


class InodeType(Enum):
    """SIMULATOR: Inode/file types (analogous to stat mode S_IFMT bits)."""
    FILE    = "REG"   # regular file (S_IFREG)
    DIR     = "DIR"   # directory (S_IFDIR)
    SYMLINK = "LNK"   # symbolic link (S_IFLNK)
    BLOCK   = "BLK"   # block device (S_IFBLK)
    CHAR    = "CHR"   # character device (S_IFCHR)
    FIFO    = "FIFO"  # named pipe (S_IFIFO)
    SOCKET  = "SOCK"  # socket (S_IFSOCK)


@dataclass
class Inode:
    """SIMULATOR: VFS inode - metadata for a filesystem object.

    Real kernel: struct inode contains device number, inode number, mode,
    link count, uid/gid, size, timestamps, block count, and a pointer to
    filesystem-specific data (i_private). Also contains operations pointers.
    SIMULATOR: We add a data bytearray for file content and a children dict
    for directories.
    """
    ino:         int
    itype:       InodeType = InodeType.FILE
    mode:        int       = 0o644
    uid:         int       = 0
    gid:         int       = 0
    size:        int       = 0
    nlink:       int       = 1
    data:        bytes     = field(default_factory=bytes)
    children:    Dict[str, int] = field(default_factory=dict)   # name -> ino (for dirs)
    link_target: str       = ""   # for symlinks
    major:       int       = 0    # for device nodes
    minor:       int       = 0    # for device nodes


@dataclass
class Dentry:
    """SIMULATOR: VFS directory entry (dentry cache entry).

    Real kernel: struct dentry caches the result of path lookups.
    It maps a (parent dentry, name) pair to an inode.
    The dcache is one of the most important performance caches in the kernel.
    SIMULATOR: We just store the path and inode number.
    """
    path: str
    ino:  int
    fs_name: str  # which filesystem this dentry belongs to


@dataclass
class OpenFile:
    """SIMULATOR: An open file description (struct file in the kernel).

    Real kernel: struct file is created when a file is opened (open/openat syscall).
    It references the inode, the dentry, and carries the current file position,
    flags (O_RDONLY, O_WRONLY, etc.), and f_ops (file operations vtable).
    Multiple file descriptors in multiple processes can reference the same struct file.
    """
    fd:       int
    path:     str
    ino:      int
    flags:    str    # "r", "w", "rw", "a"
    position: int    = 0
    fs_name:  str    = ""


class Filesystem:
    """SIMULATOR: Abstract base class for VFS filesystem drivers.

    Real kernel: Each filesystem type registers itself with the VFS via
    register_filesystem(), providing a file_system_type struct with a
    .mount() callback that returns a super_block.
    SIMULATOR: Subclasses implement these methods.
    """
    fstype: str = "unknown"

    def mount(self, source: str, target: str):
        """SIMULATOR: Mount this filesystem."""
        raise NotImplementedError

    def lookup(self, ino: int) -> Optional[Inode]:
        """SIMULATOR: Look up an inode by number."""
        raise NotImplementedError

    def lookup_name(self, parent_ino: int, name: str) -> Optional[Inode]:
        """SIMULATOR: Look up a child inode by name within a directory."""
        raise NotImplementedError

    def create(self, parent_ino: int, name: str, itype: InodeType) -> Inode:
        """SIMULATOR: Create a new inode in the given parent directory."""
        raise NotImplementedError

    def read(self, ino: int, offset: int, size: int) -> bytes:
        """SIMULATOR: Read data from a file inode."""
        raise NotImplementedError

    def write(self, ino: int, offset: int, data: bytes) -> int:
        """SIMULATOR: Write data to a file inode. Returns bytes written or -errno."""
        raise NotImplementedError

    def readdir(self, ino: int) -> List[Tuple[str, int]]:
        """SIMULATOR: List directory entries as (name, ino) pairs."""
        raise NotImplementedError

    def mkdir(self, parent_ino: int, name: str) -> Inode:
        """SIMULATOR: Create a directory."""
        return self.create(parent_ino, name, InodeType.DIR)

    @property
    def root_ino(self) -> int:
        """SIMULATOR: The inode number of the filesystem root directory."""
        raise NotImplementedError


@dataclass
class MountPoint:
    """SIMULATOR: A mounted filesystem.

    Real kernel: struct mount (vfsmount) links a filesystem's root dentry
    to its mount point in the global namespace. Mounts form a tree (mount tree).
    """
    mountpoint: str     # where it's mounted in the VFS tree (e.g. "/", "/dev")
    fs:         Filesystem
    source:     str     # device or name (e.g. "tmpfs", "/dev/sda1")


class VFS:
    """SIMULATOR: Virtual Filesystem Switch.

    Provides a unified interface over multiple mounted filesystems.
    Handles path resolution across mount points, similar to the VFS layer in Linux.

    Real kernel: The VFS layer intercepts all filesystem syscalls (open, read, write,
    mkdir, stat, etc.) and dispatches them to the appropriate filesystem driver
    via the operations tables (inode_ops, file_ops, dentry_ops, super_ops).
    Path lookup is performed by lookup_slow()/walk_component() traversing dentries.
    """

    def __init__(self, logger: KernelLogger):
        """SIMULATOR: Create a VFS with no mounted filesystems."""
        self._logger = logger
        self._mounts: List[MountPoint] = []
        self._open_files: Dict[int, OpenFile] = {}
        self._next_fd = 3  # 0/1/2 reserved for stdin/stdout/stderr

    def mount(self, mountpoint: str, fs: Filesystem, source: str = "none"):
        """SIMULATOR: Mount a filesystem at a path.

        Real kernel: do_mount() -> vfs_kern_mount() -> fs->mount() callback.
        Creates a new struct mount, links it to the mountpoint dentry.
        Subsequent path lookups that cross this mountpoint are redirected to
        the mounted filesystem's root.
        """
        fs.mount(source, mountpoint)
        mp = MountPoint(mountpoint=mountpoint, fs=fs, source=source)
        # Insert in reverse length order so longest-match is first
        self._mounts.append(mp)
        self._mounts.sort(key=lambda m: len(m.mountpoint), reverse=True)
        self._logger.info("VFS", f"mount: {fs.fstype} ({source}) -> {mountpoint}")

    def _resolve_path(self, path: str) -> Tuple[Optional[Filesystem], int]:
        """SIMULATOR: Find the filesystem and inode for the given path.

        Real kernel: __link_path_walk() iterates path components, following
        symlinks, crossing mount points (by checking mnt_root == dentry and
        following mount_hashtable), and checking permissions at each step.
        SIMULATOR: We find the best-matching mount point and walk the directory tree.
        """
        # Find the best (longest-prefix) matching mount point
        best: Optional[MountPoint] = None
        for mp in self._mounts:
            if path == mp.mountpoint or path.startswith(mp.mountpoint.rstrip("/") + "/"):
                best = mp
                break
            if mp.mountpoint == "/" and best is None:
                best = mp

        if best is None:
            return None, -2  # ENOENT

        fs = best.fs
        # Strip the mount prefix from the path
        rel = path[len(best.mountpoint):]
        if not rel or rel == "/":
            return fs, fs.root_ino

        parts = [p for p in rel.split("/") if p]
        current_ino = fs.root_ino
        for part in parts:
            child = fs.lookup_name(current_ino, part)
            if child is None:
                return fs, -2  # ENOENT
            current_ino = child.ino
        return fs, current_ino

    def open(self, path: str, flags: str = "r") -> int:
        """SIMULATOR: Open a file, returning a file descriptor.

        Real kernel: do_sys_open() -> do_filp_open() -> path_openat() ->
        vfs_open() -> file->f_op->open(). The VFS looks up the dentry,
        checks permissions, creates a struct file, assigns an fd.
        """
        fs, ino = self._resolve_path(path)
        if fs is None or ino < 0:
            self._logger.warn("VFS", f"open: path not found '{path}'")
            return -2  # ENOENT

        inode = fs.lookup(ino)
        if inode is None:
            return -2

        # For write/create: create file if not exists
        if "w" in flags or "a" in flags:
            if inode.itype == InodeType.DIR:
                # Create within directory
                parent_ino = ino
                name = path.rstrip("/").split("/")[-1]
                try:
                    inode = fs.create(parent_ino, name, InodeType.FILE)
                except FileExistsError:
                    child = fs.lookup_name(parent_ino, name)
                    if child:
                        inode = child

        fd = self._next_fd
        self._next_fd += 1
        of = OpenFile(fd=fd, path=path, ino=inode.ino, flags=flags, fs_name=fs.fstype)
        if "a" in flags:
            of.position = inode.size
        self._open_files[fd] = of
        self._logger.debug("VFS", f"open: '{path}' fd={fd} flags={flags} ino={inode.ino}")
        return fd

    def read(self, fd: int, size: int = 4096) -> bytes:
        """SIMULATOR: Read from an open file descriptor.

        Real kernel: vfs_read() -> file->f_op->read() or ->read_iter().
        Updates file position. May trigger page cache population if data not present.
        """
        of = self._open_files.get(fd)
        if of is None:
            self._logger.warn("VFS", f"read: invalid fd={fd}")
            return b""
        fs, _ = self._resolve_path(of.path)
        if fs is None:
            return b""
        data = fs.read(of.ino, of.position, size)
        of.position += len(data)
        return data

    def write(self, fd: int, data: bytes) -> int:
        """SIMULATOR: Write to an open file descriptor.

        Real kernel: vfs_write() -> file->f_op->write() or ->write_iter().
        Goes through the page cache (write-back cache) for regular files.
        For O_SYNC/O_DSYNC, triggers immediate writeback to disk.
        """
        of = self._open_files.get(fd)
        if of is None:
            self._logger.warn("VFS", f"write: invalid fd={fd}")
            return -9  # EBADF
        fs, _ = self._resolve_path(of.path)
        if fs is None:
            return -2
        n = fs.write(of.ino, of.position, data)
        if n > 0:
            of.position += n
        return n

    def close(self, fd: int) -> bool:
        """SIMULATOR: Close a file descriptor.

        Real kernel: sys_close() -> filp_close() -> fput() decrements
        the file's reference count. When it reaches zero, f_op->release() is called.
        """
        of = self._open_files.pop(fd, None)
        if of:
            self._logger.debug("VFS", f"close: fd={fd} path={of.path}")
            return True
        return False

    def readdir(self, path: str) -> List[Tuple[str, int]]:
        """SIMULATOR: List directory contents.

        Real kernel: getdents64() syscall -> vfs_readdir() -> file->f_op->iterate_shared().
        """
        fs, ino = self._resolve_path(path)
        if fs is None or ino < 0:
            return []
        return fs.readdir(ino)

    def stat(self, path: str) -> Optional[dict]:
        """SIMULATOR: Stat a path (like stat(2) syscall).

        Real kernel: vfs_stat() -> vfs_getattr() -> inode->i_op->getattr().
        Returns struct kstat (mode, ino, nlink, uid, gid, size, atime, mtime, ctime).
        """
        fs, ino = self._resolve_path(path)
        if fs is None or ino < 0:
            return None
        inode = fs.lookup(ino)
        if inode is None:
            return None
        return {
            "ino":   inode.ino,
            "type":  inode.itype.value,
            "mode":  oct(inode.mode),
            "uid":   inode.uid,
            "gid":   inode.gid,
            "size":  inode.size,
            "nlink": inode.nlink,
        }

    def mkdir(self, path: str) -> bool:
        """SIMULATOR: Create a directory.

        Real kernel: sys_mkdir() -> vfs_mkdir() -> inode->i_op->mkdir().
        """
        parent_path = "/".join(path.rstrip("/").split("/")[:-1]) or "/"
        name = path.rstrip("/").split("/")[-1]
        fs, parent_ino = self._resolve_path(parent_path)
        if fs is None or parent_ino < 0:
            self._logger.warn("VFS", f"mkdir: parent not found for '{path}'")
            return False
        try:
            fs.mkdir(parent_ino, name)
            self._logger.debug("VFS", f"mkdir: '{path}' ok")
            return True
        except (ValueError, FileExistsError) as e:
            self._logger.warn("VFS", f"mkdir: '{path}' failed: {e}")
            return False

    def create_file(self, path: str, content: bytes = b"") -> bool:
        """SIMULATOR: Create a new regular file with optional content."""
        parent_path = "/".join(path.rstrip("/").split("/")[:-1]) or "/"
        name = path.rstrip("/").split("/")[-1]
        fs, parent_ino = self._resolve_path(parent_path)
        if fs is None or parent_ino < 0:
            self._logger.warn("VFS", f"create_file: parent not found for '{path}'")
            return False
        try:
            inode = fs.create(parent_ino, name, InodeType.FILE)
            if content:
                fs.write(inode.ino, 0, content)
                inode.size = len(content)
            self._logger.debug("VFS", f"create_file: '{path}' ino={inode.ino}")
            return True
        except (ValueError, FileExistsError) as e:
            self._logger.warn("VFS", f"create_file: '{path}' failed: {e}")
            return False

    def mounts(self) -> List[dict]:
        """SIMULATOR: Return list of active mounts (like /proc/mounts)."""
        return [
            {"mountpoint": m.mountpoint, "fstype": m.fs.fstype, "source": m.source}
            for m in self._mounts
        ]

    def list_mounts(self) -> List[MountPoint]:
        """SIMULATOR: Return the list of MountPoint objects."""
        return list(self._mounts)

    def read_path(self, path: str, size: int = 4096) -> Optional[bytes]:
        """SIMULATOR: Read the contents of a file at the given path.

        Convenience helper used by the shell to cat files.
        """
        fs, ino = self._resolve_path(path)
        if fs is None or ino < 0:
            return None
        inode = fs.lookup(ino)
        if inode is None or inode.itype != InodeType.FILE:
            return None
        return fs.read(ino, 0, size)

    def write_path(self, path: str, data: bytes) -> int:
        """SIMULATOR: Write data to a file at the given path (creates if missing)."""
        fs, ino = self._resolve_path(path)
        if fs is None or ino < 0:
            # Try to create the file
            created = self.create_file(path, data)
            return len(data) if created else -2
        return fs.write(ino, 0, data)
