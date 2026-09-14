import gc
import sys
import ctypes

# Optimize Python GC threshold for low memory / high throughput environments
gc.enable()
gc.set_threshold(400, 5, 5)

def flush_ram():
    """
    Forces Python cyclic garbage collection and releases freed heap pages
    back to the OS on both Linux (glibc malloc_trim) and FreeBSD / Serv00 (jemalloc mallctl).
    """
    gc.collect()

    # 1. FreeBSD / Serv00: jemalloc is built into FreeBSD's libc (libc.so.7)
    if sys.platform.startswith(('freebsd', 'dragonfly')):
        for libname in ('libc.so.7', 'libc.so', None):
            try:
                libc = ctypes.CDLL(libname)
                if hasattr(libc, 'mallctl'):
                    libc.mallctl.argtypes = [
                        ctypes.c_char_p,
                        ctypes.c_void_p,
                        ctypes.c_void_p,
                        ctypes.c_void_p,
                        ctypes.c_size_t
                    ]
                    libc.mallctl.restype = ctypes.c_int
                    # Flush thread local caches
                    libc.mallctl(b"thread.tcache.flush", None, None, None, 0)
                    # Purge unused dirty memory pages back to FreeBSD kernel
                    libc.mallctl(b"arena.4096.purge", None, None, None, 0)
                    libc.mallctl(b"arenas.purge", None, None, None, 0)
                    break
            except Exception:
                continue

    # 2. Linux (Alwaysdata, Ubuntu, Debian): glibc malloc_trim
    elif sys.platform.startswith('linux'):
        for libname in ('libc.so.6', 'libc.so'):
            try:
                libc = ctypes.CDLL(libname)
                if hasattr(libc, 'malloc_trim'):
                    libc.malloc_trim(0)
                    break
            except Exception:
                continue

    # 3. Fallback generic check (if jemalloc was dynamically linked)
    try:
        libc = ctypes.CDLL(None)
        if hasattr(libc, 'mallctl'):
            libc.mallctl.argtypes = [
                ctypes.c_char_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_size_t
            ]
            libc.mallctl.restype = ctypes.c_int
            libc.mallctl(b"thread.tcache.flush", None, None, None, 0)
            libc.mallctl(b"arenas.purge", None, None, None, 0)
    except Exception:
        pass
