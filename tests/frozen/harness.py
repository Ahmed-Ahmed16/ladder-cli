from dataclasses import dataclass
import ctypes
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys


@dataclass(frozen=True)
class RunResult:
    exit_code: int
    lines: list[str]
    timed_out: bool = False


def make_lab(dest: Path):
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    templates = Path(__file__).parent / "lab"
    for name in ("gen.py", "ladder.toml"):
        shutil.copyfile(templates / name, dest / name)
    subprocess.run(["git", "init", "-q", str(dest)], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return dest


class _WindowsJob:
    def __init__(self):
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        self.kernel.CreateJobObjectW.restype = ctypes.c_void_p
        self.kernel.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.kernel.TerminateJobObject.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        self.kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())

    def attach_and_resume(self, child):
        if not self.kernel.AssignProcessToJobObject(self.handle, int(child._handle)):
            error = ctypes.WinError(ctypes.get_last_error())
            child.kill()
            raise error
        native = ctypes.WinDLL("ntdll")
        native.NtResumeProcess.argtypes = [ctypes.c_void_p]
        native.NtResumeProcess.restype = ctypes.c_long
        if native.NtResumeProcess(int(child._handle)) != 0:
            child.kill()
            raise OSError("resume failed")

    def kill(self):
        if not self.kernel.TerminateJobObject(self.handle, 1):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        self.kernel.CloseHandle(self.handle)


def _kill_tree(child, job=None):
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(child.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           check=False, timeout=5)
        except Exception:
            try:
                job.kill()
            except Exception:
                pass
            raise
        else:
            job.kill()
    else:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def run_ladder(build_src, argv, cwd, env_set=None, env_remove=(), wall_clock_s=60):
    env = os.environ.copy()
    env.update(env_set or {})
    for name in env_remove:
        env.pop(name, None)
    env["PYTHONPATH"] = str(Path(build_src).resolve())
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    job = _WindowsJob() if os.name == "nt" else None
    options = {"start_new_session": True} if job is None else {"creationflags": 0x00000004}
    try:
        with subprocess.Popen([sys.executable, "-m", "ladder", *argv], cwd=cwd, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, encoding="utf-8", errors="replace", **options) as child:
            if job is not None:
                job.attach_and_resume(child)
            timed_out = False
            try:
                output, _ = child.communicate(timeout=wall_clock_s)
            except subprocess.TimeoutExpired:
                timed_out = True
                _kill_tree(child, job)
                output, _ = child.communicate()
            return RunResult(child.returncode, output.splitlines(), timed_out)
    finally:
        if job is not None:
            job.close()
