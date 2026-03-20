"""Tests for the VFS simulation."""
import pytest
from computekernel_edu.vfs import VFS, InodeType
from computekernel_edu.fs_tmpfs import TmpFS
from computekernel_edu.logger import KernelLogger


@pytest.fixture
def vfs_env():
    log = KernelLogger()
    log._serial_sink = False
    fs = TmpFS(log)
    vfs = VFS(log)
    vfs.mount("/", fs)
    return vfs, fs, log


def test_mount(vfs_env):
    vfs, fs, log = vfs_env
    assert len(vfs._mounts) == 1
    assert vfs._mounts[0].path == "/"


def test_mkdir_and_ls(vfs_env):
    vfs, fs, log = vfs_env
    from computekernel_edu.process import Credentials
    creds = Credentials()
    vfs.mkdir("/testdir", creds)
    entries = vfs.readdir("/")
    assert "testdir" in entries or any("testdir" in e for e in entries)


def test_create_and_read_file(vfs_env):
    vfs, fs, log = vfs_env
    from computekernel_edu.process import Credentials
    creds = Credentials()
    vfs.mkdir("/etc", creds)
    inode = fs.create(fs.root_ino, "hostname", InodeType.FILE)
    fs.write(inode.ino, 0, b"computekernel\n")
    data = fs.read(inode.ino, 0, 64)
    assert data == b"computekernel\n"


def test_tmpfs_create_dir():
    log = KernelLogger()
    log._serial_sink = False
    fs = TmpFS(log)
    d = fs.mkdir(fs.root_ino, "proc")
    assert d.itype == InodeType.DIR


def test_tmpfs_write_read():
    log = KernelLogger()
    log._serial_sink = False
    fs = TmpFS(log)
    f = fs.create(fs.root_ino, "test.txt", InodeType.FILE)
    written = fs.write(f.ino, 0, b"hello world")
    assert written == 11
    data = fs.read(f.ino, 0, 100)
    assert data == b"hello world"


def test_tmpfs_readdir():
    log = KernelLogger()
    log._serial_sink = False
    fs = TmpFS(log)
    fs.mkdir(fs.root_ino, "bin")
    fs.mkdir(fs.root_ino, "etc")
    fs.create(fs.root_ino, "README", InodeType.FILE)
    entries = fs.readdir(fs.root_ino)
    names = [e[0] for e in entries]
    assert "bin" in names
    assert "etc" in names
    assert "README" in names


def test_stat_path(vfs_env):
    vfs, fs, log = vfs_env
    inode = vfs.stat("/")
    assert inode is not None
    assert inode.itype == InodeType.DIR
