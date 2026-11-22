"""Named Windows mutexes, so two clocks or two runners never overlap. Tests add AURUM_DESK_MUTEX_SUFFIX so they never
collide with a desk that is running on the same PC.
"""
import ctypes
import os
import sys
from contextlib import contextmanager

WAIT_OBJECT_0, WAIT_ABANDONED, ERROR_ALREADY_EXISTS, MUTEX_ALL_ACCESS = 0, 0x80, 183, 0x001F0001


def _name(name):
    return name + os.environ.get("AURUM_DESK_MUTEX_SUFFIX", "")


def _k32():
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateMutexW.restype = ctypes.c_void_p
    k.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    k.OpenMutexW.restype = ctypes.c_void_p
    k.OpenMutexW.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_wchar_p]
    k.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    k.WaitForSingleObject.restype = ctypes.c_uint32
    k.ReleaseMutex.argtypes = [ctypes.c_void_p]
    k.CloseHandle.argtypes = [ctypes.c_void_p]
    return k


@contextmanager
def hold(name):
    """Yields True if this process now owns the mutex, False if another one does."""
    if sys.platform != "win32":
        yield True
        return
    k = _k32()
    h = k.CreateMutexW(None, False, _name(name))
    if not h:
        yield False
        return
    if k.WaitForSingleObject(h, 0) not in (WAIT_OBJECT_0, WAIT_ABANDONED):
        k.CloseHandle(h)
        yield False
        return
    try:
        yield True
    finally:
        k.ReleaseMutex(h)
        k.CloseHandle(h)


def free(name):
    """True when nobody holds the mutex."""
    if sys.platform != "win32":
        return True
    k = _k32()
    h = k.OpenMutexW(MUTEX_ALL_ACCESS, False, _name(name))
    if not h:
        return True
    try:
        if k.WaitForSingleObject(h, 0) in (WAIT_OBJECT_0, WAIT_ABANDONED):
            k.ReleaseMutex(h)
            return True
        return False
    finally:
        k.CloseHandle(h)
