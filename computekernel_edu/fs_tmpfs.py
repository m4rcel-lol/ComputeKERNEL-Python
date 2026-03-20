"""
SIMULATOR: tmpfs - in-memory temporary filesystem.
Models a RAM-backed filesystem (like Linux tmpfs) for use as rootfs during boot.

Real kernel: tmpfs pages live in the page cache and can be swapped.
SIMULATOR: We just use Python dicts.
"""

from typing import Dict, List, Optional, Tuple
from .vfs import Filesystem, Inode, InodeType
from .logger import KernelLogger


class TmpFS(Filesystem):
    """SIMULATOR: In-memory filesystem implementing the VFS Filesystem interface.

    Supports create, read, write, readdir, lookup for files and directories.
    Used as rootfs in the simulated boot sequence.
    """
    fstype = "tmpfs"

    def __init__(self, logger: KernelLogger):
        """SIMULATOR: Create a new tmpfs with an empty root directory (ino=1)."""
        self._logger = logger
        self._inodes: Dict[int, Inode] = {}
        self._next_ino = 1
        # Create root inode
        root = self._new_inode(InodeType.DIR, mode=0o755)
        root.uid = 0
        root.gid = 0

    def _new_inode(self, itype: InodeType, mode: int = 0o644) -> Inode:
        """SIMULATOR: Allocate a new inode with the next available number."""
        ino = self._next_ino
        self._next_ino += 1
        inode = Inode(ino=ino, itype=itype, mode=mode)
        self._inodes[ino] = inode
        return inode

    @property
    def root_ino(self) -> int:
        """SIMULATOR: Root directory is always inode 1 in tmpfs."""
        return 1

    def mount(self, source: str, target: str):
        """SIMULATOR: Mount this tmpfs at the given target path."""
        self._logger.info("FS", f"tmpfs: mounted at {target} (source={source})")

    def lookup(self, ino: int) -> Optional[Inode]:
        """SIMULATOR: Look up an inode by number."""
        return self._inodes.get(ino)

    def lookup_name(self, parent_ino: int, name: str) -> Optional[Inode]:
        """SIMULATOR: Look up a child by name in a directory inode."""
        parent = self._inodes.get(parent_ino)
        if parent is None or parent.itype != InodeType.DIR:
            return None
        child_ino = parent.children.get(name)
        if child_ino is None:
            return None
        return self._inodes.get(child_ino)

    def create(self, parent_ino: int, name: str, itype: InodeType) -> Inode:
        """SIMULATOR: Create a new file or directory in a parent directory."""
        parent = self._inodes.get(parent_ino)
        if parent is None or parent.itype != InodeType.DIR:
            raise ValueError(f"tmpfs.create: parent {parent_ino} not a dir")
        if name in parent.children:
            raise FileExistsError(f"tmpfs.create: '{name}' already exists")
        child = self._new_inode(itype)
        parent.children[name] = child.ino
        self._logger.debug("FS", f"tmpfs.create: parent={parent_ino} name={name} ino={child.ino} type={itype.value}")
        return child

    def read(self, ino: int, offset: int, size: int) -> bytes:
        """SIMULATOR: Read data from a file inode."""
        inode = self._inodes.get(ino)
        if inode is None:
            return b""
        if inode.itype != InodeType.FILE:
            return b""
        return inode.data[offset:offset + size]

    def write(self, ino: int, offset: int, data: bytes) -> int:
        """SIMULATOR: Write data to a file inode."""
        inode = self._inodes.get(ino)
        if inode is None:
            return -2  # ENOENT
        if inode.itype != InodeType.FILE:
            return -22  # EINVAL
        # Extend if needed
        if offset > len(inode.data):
            inode.data = inode.data + b'\x00' * (offset - len(inode.data))
        inode.data = inode.data[:offset] + data + inode.data[offset + len(data):]
        inode.size = len(inode.data)
        return len(data)

    def readdir(self, ino: int) -> List[Tuple[str, int]]:
        """SIMULATOR: List directory entries."""
        inode = self._inodes.get(ino)
        if inode is None or inode.itype != InodeType.DIR:
            return []
        result = [(".", ino), ("..", ino)]
        result.extend(inode.children.items())
        return result

    def mkdir(self, parent_ino: int, name: str) -> Inode:
        """SIMULATOR: Create a directory."""
        return self.create(parent_ino, name, InodeType.DIR)

    def symlink(self, parent_ino: int, name: str, target: str) -> Inode:
        """SIMULATOR: Create a symbolic link."""
        sl = self.create(parent_ino, name, InodeType.SYMLINK)
        sl.link_target = target
        return sl

    def mknod(self, parent_ino: int, name: str, major: int, minor: int, itype: InodeType) -> Inode:
        """SIMULATOR: Create a device node."""
        dev = self.create(parent_ino, name, itype)
        dev.major = major
        dev.minor = minor
        return dev

    def stats(self) -> dict:
        """SIMULATOR: Return filesystem usage statistics."""
        files = sum(1 for i in self._inodes.values() if i.itype == InodeType.FILE)
        dirs = sum(1 for i in self._inodes.values() if i.itype == InodeType.DIR)
        total_bytes = sum(len(i.data) for i in self._inodes.values())
        return {"inodes": len(self._inodes), "files": files, "dirs": dirs, "bytes_used": total_bytes}
