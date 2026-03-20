"""
SIMULATOR: Ext2-inspired educational filesystem model.
NOT real ext2 parsing. Models ext2 concepts (superblock, block groups, inodes)
in Python for educational purposes only.

Real ext2: Block groups contain a superblock copy, block bitmap, inode bitmap,
inode table, and data blocks. Inodes store metadata; data stored in blocks
referenced by direct/indirect/doubly-indirect block pointers.

SIMULATOR: We use Python dicts for everything.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from .vfs import Filesystem, Inode, InodeType
from .logger import KernelLogger


@dataclass
class Ext2Superblock:
    """SIMULATOR: Models ext2 superblock metadata (not real on-disk format)."""
    total_inodes:    int  = 1024
    total_blocks:    int  = 8192
    free_inodes:     int  = 1023
    free_blocks:     int  = 8180
    block_size:      int  = 4096
    inodes_per_group: int = 128
    blocks_per_group: int = 1024
    volume_name:     str  = "ext2-sim"
    magic:           int  = 0xEF53  # real ext2 magic number


@dataclass
class Ext2BlockGroup:
    """SIMULATOR: Models an ext2 block group descriptor."""
    group_id:    int
    block_bitmap: int = 0
    inode_bitmap: int = 0
    inode_table:  int = 0
    free_blocks:  int = 1024
    free_inodes:  int = 128
    used_dirs:    int = 0


class Ext2FS(Filesystem):
    """SIMULATOR: Educational ext2-inspired filesystem.

    Demonstrates ext2 structural concepts (superblock, block groups, inode table)
    without implementing the real on-disk format.
    """
    fstype = "ext2"

    def __init__(self, logger: KernelLogger, volume_name: str = "ext2-sim"):
        """SIMULATOR: Create a new ext2-sim volume with a root directory at inode 2."""
        self._logger = logger
        self._superblock = Ext2Superblock(volume_name=volume_name)
        self._block_groups = [Ext2BlockGroup(group_id=i) for i in range(8)]
        self._inodes: Dict[int, Inode] = {}
        self._next_ino = 2  # ext2 root is inode 2
        # Create root inode (ext2 convention: ino 2 is root)
        root = Inode(ino=2, itype=InodeType.DIR, mode=0o755)
        self._inodes[2] = root
        self._superblock.free_inodes -= 1

    @property
    def root_ino(self) -> int:
        """SIMULATOR: ext2 root is always inode 2."""
        return 2

    def mount(self, source: str, target: str):
        """SIMULATOR: Mount this ext2-sim volume."""
        self._logger.info("FS", f"ext2-sim: mounted '{self._superblock.volume_name}' at {target}")
        self._logger.info("FS", f"ext2-sim: magic=0x{self._superblock.magic:04x} "
                          f"block_size={self._superblock.block_size} "
                          f"total_inodes={self._superblock.total_inodes}")

    def lookup(self, ino: int) -> Optional[Inode]:
        """SIMULATOR: Look up an inode by number."""
        return self._inodes.get(ino)

    def lookup_name(self, parent_ino: int, name: str) -> Optional[Inode]:
        """SIMULATOR: Look up a child inode by name in a directory."""
        parent = self._inodes.get(parent_ino)
        if parent is None or parent.itype != InodeType.DIR:
            return None
        child_ino = parent.children.get(name)
        if child_ino is None:
            return None
        return self._inodes.get(child_ino)

    def create(self, parent_ino: int, name: str, itype: InodeType) -> Inode:
        """SIMULATOR: Allocate a new ext2 inode and add a directory entry."""
        parent = self._inodes.get(parent_ino)
        if parent is None or parent.itype != InodeType.DIR:
            raise ValueError(f"ext2.create: parent {parent_ino} not a dir")
        if name in parent.children:
            raise FileExistsError(f"ext2.create: '{name}' already exists")
        ino = self._next_ino
        self._next_ino += 1
        inode = Inode(ino=ino, itype=itype)
        self._inodes[ino] = inode
        parent.children[name] = ino
        self._superblock.free_inodes -= 1
        self._logger.debug("FS", f"ext2.create: ino={ino} name={name} type={itype.value}")
        return inode

    def read(self, ino: int, offset: int, size: int) -> bytes:
        """SIMULATOR: Read data from a file inode."""
        inode = self._inodes.get(ino)
        if inode is None or inode.itype != InodeType.FILE:
            return b""
        return inode.data[offset:offset + size]

    def write(self, ino: int, offset: int, data: bytes) -> int:
        """SIMULATOR: Write data to a file inode."""
        inode = self._inodes.get(ino)
        if inode is None or inode.itype != InodeType.FILE:
            return -22
        if offset > len(inode.data):
            inode.data = inode.data + b'\x00' * (offset - len(inode.data))
        inode.data = inode.data[:offset] + data + inode.data[offset + len(data):]
        inode.size = len(inode.data)
        blocks_used = (inode.size + self._superblock.block_size - 1) // self._superblock.block_size
        self._logger.debug("FS", f"ext2.write: ino={ino} size={inode.size} blocks={blocks_used}")
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
        """SIMULATOR: Create a directory inode."""
        return self.create(parent_ino, name, InodeType.DIR)

    def superblock_info(self) -> dict:
        """SIMULATOR: Return superblock information for educational display."""
        sb = self._superblock
        return {
            "magic":        hex(sb.magic),
            "volume_name":  sb.volume_name,
            "block_size":   sb.block_size,
            "total_inodes": sb.total_inodes,
            "free_inodes":  sb.free_inodes,
            "total_blocks": sb.total_blocks,
            "free_blocks":  sb.free_blocks,
            "block_groups": len(self._block_groups),
        }
