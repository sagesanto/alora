# Sage Santomenna 2026
# don't let maestro memory limit grow beyond a certain amount
# works on windows (Job) and linux/mac (resource.setrlimit)

import sys


def enforce_memory_limit(max_bytes: int) -> None:
    if sys.platform.startswith("linux") or sys.platform == "darwin":
        enforce_posix_limit(max_bytes)
    elif sys.platform == "win32":
        enforce_windows_limit(max_bytes)


def enforce_posix_limit(max_bytes: int) -> None:
    import resource

    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    new_hard = max_bytes if hard == resource.RLIM_INFINITY else min(max_bytes, hard)
    new_soft = min(max_bytes, new_hard)
    resource.setrlimit(resource.RLIMIT_AS, (new_soft, new_hard))


def enforce_windows_limit(max_bytes: int) -> None:
    # this is some serious dark magic bc everything is worse on windows
    # https://github.com/danielhanchen/unsloth-fp8-fix/blob/main/studio/backend/utils/process_lifetime.py
    
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]

    JobObjectExtendedLimitInformation = 9
    JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
            ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        print("Failed to limit memory: couldn't create job object")
        return

    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_JOB_MEMORY
    info.JobMemoryLimit = max_bytes

    ok = kernel32.SetInformationJobObject(job,JobObjectExtendedLimitInformation,ctypes.byref(info),ctypes.sizeof(info),)
    if not ok:
        return

    kernel32.AssignProcessToJobObject(job, kernel32.GetCurrentProcess())
