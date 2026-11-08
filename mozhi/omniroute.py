"""Start OmniRoute when Mozhi needs it, and stop it on exit only if Mozhi was the one that started it.

    external   an OmniRoute was already answering, so Mozhi leaves it alone (never stops it)
    starting   Mozhi launched `omniroute serve` and is waiting for it to answer
    started    Mozhi launched it and it is healthy; it will be stopped when Mozhi exits
    failed     it could not be started (not installed, crashed, or too slow); general questions explain why
    remote     the endpoint is not on this machine, so there is nothing to start
    off        no endpoint configured, or MOZHI_MANAGE_OMNIROUTE=0

On Windows the child is placed in a job object that kills it when Mozhi exits for any reason, including
closing the console window or killing mozhi.exe, so it cannot be left behind by accident.
"""

import atexit
import logging
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

log = logging.getLogger("mozhi.omniroute")
LOCAL = {"localhost", "127.0.0.1", "::1", "[::1]"}
READY_TIMEOUT_S = float(os.getenv("OMNIROUTE_READY_TIMEOUT_S", "90"))


def _kill_on_close_job(proc: subprocess.Popen):
    """Windows only: tie the child's lifetime to this process. Returns the job handle (keep it referenced)."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    class Basic(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class Io(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in ("r", "w", "o", "rb", "wb", "ob")]

    class Extended(ctypes.Structure):
        _fields_ = [("Basic", Basic), ("Io", Io), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateJobObjectW.restype = wintypes.HANDLE
    k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    job = k.CreateJobObjectW(None, None)
    if not job:
        return None
    info = Extended()
    info.Basic.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    k.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
    k.AssignProcessToJobObject(job, wintypes.HANDLE(int(proc._handle)))
    return job


class OmniRoute:
    def __init__(self) -> None:
        self.state = "off"
        self.detail = ""
        self.proc: subprocess.Popen | None = None
        self._job = None
        self._lock = threading.Lock()
        atexit.register(self.stop)

    # ---- helpers ----
    @staticmethod
    def _target(endpoint: str) -> tuple[str, int, str] | None:
        u = urlparse(endpoint)
        if not u.hostname:
            return None
        return u.hostname, u.port or (443 if u.scheme == "https" else 80), f"{u.scheme}://{u.netloc}"

    @staticmethod
    def healthy(base: str, timeout: float = 1.5) -> bool:
        try:
            return httpx.get(base + "/api/health", timeout=timeout).status_code == 200
        except httpx.HTTPError:
            return False

    @staticmethod
    def executable() -> str | None:
        """Find omniroute on PATH without ever picking up a copy from the current directory."""
        explicit = os.getenv("OMNIROUTE_BIN")
        if explicit:
            return explicit if os.path.isabs(explicit) and os.path.isfile(explicit) else None
        cwd = os.path.normcase(os.path.realpath(os.getcwd()))
        dirs = [d for d in os.environ.get("PATH", "").split(os.pathsep)
                if d and d != "." and os.path.isabs(d) and os.path.normcase(os.path.realpath(d)) != cwd]
        found = shutil.which("omniroute", path=os.pathsep.join(dirs))
        return found if found and os.path.isabs(found) else None

    # ---- lifecycle ----
    def ensure(self, endpoint: str) -> None:
        """Make sure something answers at the endpoint. Blocking, so run it in a thread."""
        if os.getenv("MOZHI_MANAGE_OMNIROUTE", "1") == "0" or not endpoint:
            self.state = "off"
            return
        target = self._target(endpoint)
        if not target:
            self.state = "off"
            return
        host, port, base = target
        if host not in LOCAL:
            self.state, self.detail = "remote", ""
            return
        if self.healthy(base):
            self.state, self.detail = "external", "already running"
            return
        exe = self.executable()
        if not exe:
            self.state, self.detail = "failed", "OmniRoute is not installed"
            return
        with self._lock:
            self.state, self.detail = "starting", "launching"
            cmd = [exe, "serve", "--no-open", "--no-tray", "--port", str(port)]
            flags = (subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == "nt" else 0
            try:
                self.proc = subprocess.Popen(cmd, cwd=str(Path.home()), stdin=subprocess.DEVNULL,
                                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                             creationflags=flags, start_new_session=os.name != "nt")
            except OSError as exc:
                log.warning("could not start OmniRoute: %s", exc)
                self.state, self.detail = "failed", "could not start OmniRoute"
                return
            self._job = _kill_on_close_job(self.proc)
        deadline = time.monotonic() + READY_TIMEOUT_S
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                log.warning("OmniRoute exited with code %s", self.proc.returncode)
                self.state, self.detail = "failed", "OmniRoute stopped unexpectedly"
                return
            if self.healthy(base):
                self.state, self.detail = "started", "started by Mozhi"
                return
            time.sleep(1)
        self.state, self.detail = "failed", "OmniRoute did not answer in time"
        self.stop()

    def stop(self) -> None:
        """Stop OmniRoute, but only a copy this object started."""
        with self._lock:
            p, self.proc = self.proc, None
        if not p or p.poll() is not None:
            return
        if os.name == "nt":
            self._terminate_windows(p)
        else:
            import signal

            try:
                os.killpg(os.getpgid(p.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()
        if self.state in ("started", "starting"):
            self.state, self.detail = "off", "stopped"

    def _terminate_windows(self, p: subprocess.Popen) -> None:
        """Kill the child and everything it started: the job object if there is one, else taskkill by full path."""
        import ctypes
        from ctypes import wintypes

        if self._job:
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
            if kernel.TerminateJobObject(self._job, 1):
                return
        system = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "taskkill.exe")
        subprocess.run([system, "/PID", str(p.pid), "/T", "/F"], capture_output=True, check=False)

    def ensure_in_background(self, endpoint: str) -> None:
        threading.Thread(target=self.ensure, args=(endpoint,), name="omniroute", daemon=True).start()


manager = OmniRoute()

