"""Exercise the harness with a local Python package, not PATH ladder."""

import ctypes
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from unittest.mock import Mock, patch

from tests.frozen import harness, replay
from tests.frozen.harness import make_lab, run_ladder


def process_is_alive(pid):
    if os.name == "nt":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_uint32()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
                raise ctypes.WinError(ctypes.get_last_error())
            return code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # A killed child can remain a zombie until its system parent reaps it.
    status = Path(f"/proc/{pid}/stat")
    try:
        if status.read_text().split()[2] == "Z":
            return False
    except FileNotFoundError:
        pass
    return True


def stop_process(pid):
    """Clean up a stub if the timeout assertion fails."""
    if not process_is_alive(pid):
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    else:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def read_pids(path):
    try:
        pids = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(pids, list) or not all(type(pid) is int for pid in pids):
        return []
    return pids


class FrozenHarnessTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.build = self.root / "build"
        package = self.build / "ladder"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("", encoding="utf-8")
        self.entry = package / "__main__.py"
        self.cwd = self.root / "work"
        self.cwd.mkdir()

    def stub(self, source):
        self.entry.write_text(textwrap.dedent(source), encoding="utf-8")

    def test_merges_stdout_and_stderr_in_order(self):
        self.stub('''
            import os
            os.write(1, b"out-first\\n")
            os.write(2, b"err-second\\n")
            os.write(1, b"out-third\\n")
        ''')
        result = run_ladder(self.build, [], self.cwd)
        self.assertEqual(result.lines, ["out-first", "err-second", "out-third"])

    def test_keeps_child_exit_code(self):
        self.stub("raise SystemExit(7)")
        result = run_ladder(self.build, [], self.cwd)
        self.assertEqual(result.exit_code, 7)
        self.assertFalse(result.timed_out)

    def test_uses_requested_build_cwd_and_argv(self):
        self.stub('''
            import json
            from pathlib import Path
            import sys
            print(json.dumps([str(Path.cwd()), sys.argv[1:]]))
        ''')
        result = run_ladder(self.build, ["fake-task", "arg with space"], self.cwd)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(json.loads(result.lines[0]),
                         [str(self.cwd), ["fake-task", "arg with space"]])

    def test_env_can_remove_inherited_claudecode_and_set_child_values(self):
        self.stub('''
            import json
            import os
            print(json.dumps({key: os.environ.get(key) for key in
                              ("CLAUDECODE", "FROZEN_TEST_VALUE")}))
        ''')
        with patch.dict(os.environ, {"CLAUDECODE": "inherited", "FROZEN_TEST_VALUE": "old"}):
            result = run_ladder(self.build, [], self.cwd,
                                env_set={"FROZEN_TEST_VALUE": "child"},
                                env_remove=("CLAUDECODE",))
            self.assertEqual(os.environ["CLAUDECODE"], "inherited")
            self.assertEqual(os.environ["FROZEN_TEST_VALUE"], "old")
        self.assertEqual(result.exit_code, 0)
        self.assertFalse(result.timed_out)
        self.assertEqual(json.loads(result.lines[0]),
                         {"CLAUDECODE": None, "FROZEN_TEST_VALUE": "child"})

    def test_timeout_stops_stub_and_descendant_within_seconds(self):
        self.stub('''
            import json
            import os
            from pathlib import Path
            import subprocess
            import sys
            import time
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
            Path("pids.json").write_text(json.dumps([os.getpid(), child.pid]))
            print("ready", flush=True)
            time.sleep(60)
        ''')
        started = time.monotonic()
        try:
            result = run_ladder(self.build, [], self.cwd, wall_clock_s=1.5)
            elapsed = time.monotonic() - started
            self.assertTrue(result.timed_out)
            self.assertNotEqual(result.exit_code, 0)
            self.assertLess(elapsed, 8)
            pid_file = self.cwd / "pids.json"
            pids = []
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                pids = read_pids(pid_file)
                if len(pids) == 2 and not any(process_is_alive(pid) for pid in pids):
                    break
                time.sleep(0.05)
            self.assertEqual(len(pids), 2, "stub did not record both process IDs")
            self.assertFalse(any(process_is_alive(pid) for pid in pids))
        finally:
            for pid in reversed(read_pids(self.cwd / "pids.json")):
                try:
                    stop_process(pid)
                except (OSError, subprocess.SubprocessError):
                    pass

    def test_make_lab_creates_git_repo(self):
        lab = self.root / "lab"
        make_lab(lab)
        git = subprocess.run(["git", "-C", str(lab), "rev-parse", "--is-inside-work-tree"],
                             capture_output=True, text=True, timeout=10)
        self.assertEqual(git.returncode, 0, git.stderr)
        self.assertEqual(git.stdout.strip(), "true")

    def test_make_lab_copies_lab_files(self):
        lab = make_lab(self.root / "lab")
        templates = Path(harness.__file__).parent / "lab"
        for name in ("ladder.toml", "gen.py"):
            with self.subTest(name=name):
                self.assertEqual((lab / name).read_bytes(), (templates / name).read_bytes())

    def replay_args(self):
        return ["--build-src", str(self.build), "--label", "test",
                "--out", str(self.root / "scores.json")]

    def test_usage_errors_return_2(self):
        missing_package = self.root / "no-ladder"
        missing_package.mkdir()
        missing_build = self.replay_args()
        missing_build[1] = str(missing_package)
        cases = [[], ["--unknown"], ["--build-src"],
                 ["--label", "test", "--out", str(self.root / "unused.json")],
                 self.replay_args() + ["--only", "B9"], missing_build]
        for args in cases:
            with self.subTest(args=args), redirect_stderr(io.StringIO()):
                self.assertEqual(replay.main(args), 2)

    def test_only_deduplicates_rows_in_requested_order(self):
        counter = self.root / "child-calls.txt"
        self.stub(f'''
            from pathlib import Path
            with Path({str(counter)!r}).open("a", encoding="utf-8") as stream:
                stream.write("call\\n")
            raise SystemExit(3)
        ''')
        contract = json.loads((replay.FROZEN / "contracts.json").read_text(encoding="utf-8"))
        counts = {"B1": len(contract["replay_cases"]["b1_cases"]),
                  "B3": len(contract["builds"]["B3a_B3b"]["replay"])}
        for only, expected in (("B1,B1", ["B1"]),
                               ("B3,B1,B3", ["B3", "B1"])):
            with self.subTest(only=only):
                counter.unlink(missing_ok=True)
                self.assertEqual(replay.main(self.replay_args() + ["--only", only]), 0)
                data = json.loads((self.root / "scores.json").read_text(encoding="utf-8"))
                rows = [row for row in data["rows"] if row in {"B1", "B2", "B3", "B4"}]
                self.assertEqual(rows, expected)
                self.assertEqual(len(counter.read_text(encoding="utf-8").splitlines()),
                                 sum(counts[row] for row in expected))

    def test_bad_contract_returns_2_and_only_error_class(self):
        frozen = self.root / "bad-frozen"
        frozen.mkdir()
        for contract, error_class in (({}, "KeyError"), ([], "TypeError")):
            with self.subTest(error_class=error_class):
                (frozen / "contracts.json").write_text(json.dumps(contract), encoding="utf-8")
                out, err = io.StringIO(), io.StringIO()
                with (patch.object(replay, "FROZEN", frozen), redirect_stdout(out),
                      redirect_stderr(err)):
                    code = replay.main(self.replay_args())
                self.assertEqual(code, 2)
                self.assertEqual(out.getvalue(), "")
                self.assertEqual(err.getvalue(), error_class + "\n")

    def test_gh_shims_use_current_python_without_python_on_path(self):
        script = self.root / "shim script.py"
        script.write_text("import json, sys\nprint(json.dumps([sys.executable, sys.argv[1:]]))\n",
                          encoding="utf-8")
        folder = self.root / "shim bin"
        replay.gh_shims(folder, script)
        shim = folder / ("gh.cmd" if os.name == "nt" else "gh")
        command = [str(shim), "a b"]
        child = subprocess.run(command, env=dict(os.environ, PATH=str(folder)),
                               shell=os.name == "nt", capture_output=True, text=True, timeout=5)
        self.assertEqual(child.returncode, 0, child.stderr)
        self.assertEqual(json.loads(child.stdout), [sys.executable, ["a b"]])

    @unittest.skipUnless(os.name == "nt", "Windows taskkill cleanup")
    def test_kill_tree_keeps_first_taskkill_error_after_job_cleanup_error(self):
        first = OSError("taskkill error")
        job = Mock()
        job.kill.side_effect = RuntimeError("job cleanup error")
        with patch.object(harness.subprocess, "run", side_effect=first):
            with self.assertRaises(OSError) as caught:
                harness._kill_tree(Mock(pid=12345), job)
        self.assertIs(caught.exception, first)
        job.kill.assert_called_once_with()

    def test_generator_places_error_and_flushes_marker_with_requested_exit(self):
        lab = make_lab(self.root / "lab")
        child = subprocess.run([sys.executable, str(lab / "gen.py"), "3", "4", "first",
                                "--at", "2", "replacement", "--sleep", "0"],
                               env=dict(os.environ, LAB_MARKER="fixture-label"),
                               capture_output=True, text=True, timeout=5)
        self.assertEqual(child.returncode, 4)
        self.assertEqual(child.stderr, "")
        self.assertEqual(child.stdout.splitlines(),
                         ["first", "line 1 of 3", "replacement", "line 3 of 3", "fixture-label"])

    def test_b3_reads_relative_log_with_the_frozen_command(self):
        contract = json.loads((Path(__file__).parent / "contracts.json").read_text(encoding="utf-8"))
        spec = contract["builds"]["B3a_B3b"]["replay"]["longfail150_agent_mode"]
        read = spec["log_read"]
        argv = [part.format(log="full.log", pattern=read["pattern"])
                for part in read["argv_template"]]
        self.stub(f'''
            from pathlib import Path
            import sys
            if sys.argv[1:] == ["longfail150"]:
                Path("full.log").write_text({read["pattern"]!r}, encoding="utf-8")
                print("FAIL log: full.log", flush=True)
                raise SystemExit(1)
            if sys.argv[1:] != {argv!r}:
                raise SystemExit(9)
            print(Path("full.log").read_text(encoding="utf-8"))
        ''')
        score = replay.b3_case(self.build, spec, {})
        self.assertEqual(score["status"], "PASS")
        self.assertTrue(score["checks"]["log_exit"])
        self.assertTrue(score["checks"]["log_contains_result"])


if __name__ == "__main__":
    unittest.main()
