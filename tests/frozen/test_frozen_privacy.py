from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from tests.frozen import replay
from tests.frozen.harness import make_lab, run_ladder


MARKER = json.loads((Path(__file__).parent / "contracts.json").read_text(
    encoding="utf-8"))["privacy"]["fake_secret_marker"]


class PrivacyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.build = self.root / "stub-src"
        self.package = self.build / "ladder"
        self.package.mkdir(parents=True)
        (self.package / "__init__.py").write_text("", encoding="utf-8")
        self.scratch = self.root / "scratch"
        self.scratch.mkdir()

    def assert_private_replay(self, only="B1,B2,B3"):
        scores = self.root / "scores.json"
        report = self.root / "report.md"
        out, err = io.StringIO(), io.StringIO()
        with (patch.dict(os.environ, {"LAB_MARKER": MARKER}),
              patch.object(tempfile, "tempdir", str(self.scratch)),
              redirect_stdout(out), redirect_stderr(err)):
            code = replay.main(["--build-src", str(self.build), "--label", "privacy",
                                "--out", str(scores), "--md", str(report),
                                "--only", only])
        self.assertEqual(code, 0)
        self.assertEqual(list(self.scratch.iterdir()), [])
        for value in (scores.read_text(encoding="utf-8"), report.read_text(encoding="utf-8"),
                      out.getvalue(), err.getvalue()):
            self.assertNotIn(MARKER, value)
        return json.loads(scores.read_text(encoding="utf-8"))

    def marker_stub(self):
        (self.package / "__main__.py").write_text(
            "import os, subprocess, sys\n"
            "marker = os.environ['LAB_MARKER']\n"
            "print(marker, flush=True)\n"
            "print(marker, file=sys.stderr, flush=True)\n"
            "if sys.argv[1:] == ['long']:\n"
            "    raise RuntimeError(marker)\n"
            "subprocess.run([sys.executable, 'gen.py', '1', '0'], check=True)\n"
            "raise SystemExit(3)\n", encoding="utf-8")

    def test_child_stdout_stderr_failure_crash_and_generator_env_stay_private(self):
        self.marker_stub()
        data = self.assert_private_replay()
        self.assertGreater(data["verdicts"]["B1"]["fail_count"], 0)

    def test_marker_stub_reaches_stdout_stderr_and_generator(self):
        self.marker_stub()
        lab = make_lab(self.root / "lab")
        result = run_ladder(self.build, ["fail"], lab, env_set={"LAB_MARKER": MARKER},
                            env_remove=("CLAUDECODE",))
        self.assertEqual(result.exit_code, 3)
        self.assertEqual(result.lines.count(MARKER), 3)

    def test_import_exception_traceback_stays_private(self):
        (self.package / "__init__.py").write_text(
            f"raise RuntimeError({MARKER!r})\n", encoding="utf-8")
        (self.package / "__main__.py").write_text("", encoding="utf-8")
        self.assert_private_replay()

    def test_child_exception_stays_private(self):
        (self.package / "__main__.py").write_text(
            f"raise RuntimeError({MARKER!r})\n", encoding="utf-8")
        data = self.assert_private_replay()
        for row in ("B1", "B2", "B3"):
            for score in data["rows"][row]:
                if score["status"] != "NOT_RUN":
                    self.assertEqual(score["status"], "FAIL")

    def test_harness_exception_records_only_type_name(self):
        def fail():
            raise RuntimeError(MARKER)

        score = replay.safe_case("stub-error", fail)
        self.assertEqual(score["status"], "FAIL")
        self.assertEqual(score["observed"], {"error_class": "RuntimeError"})
        self.assertNotIn(MARKER, json.dumps(score))

    def copy_frozen(self):
        frozen = self.root / "frozen"
        frozen.mkdir()
        shutil.copyfile(replay.FROZEN / "contracts.json", frozen / "contracts.json")
        return frozen

    def test_failed_pr_log_stays_private_through_real_gh_shim(self):
        frozen = self.copy_frozen()
        shutil.copyfile(replay.FROZEN / "fake_gh.py", frozen / "fake_gh.py")
        shutil.copytree(replay.FROZEN / "pr_states", frozen / "pr_states")
        state_path = frozen / "pr_states" / "pr-one-failed.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        for call in state["calls"]:
            if call["match"][:2] == ["run", "view"] and "--log-failed" in call["match"]:
                call["stdout"] += MARKER + "\n"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        proof = self.root / "gh-proof.txt"
        (self.package / "__main__.py").write_text(
            "import os, shutil, subprocess, sys\n"
            "from pathlib import Path\n"
            "if sys.argv[1:] == ['pr', 'status']:\n"
            "    shim = shutil.which('gh')\n"
            "    result = subprocess.run([shim, 'run', 'view', '201', '--log-failed'],\n"
            "                            shell=os.name == 'nt', capture_output=True,\n"
            "                            text=True, check=True)\n"
            "    print(result.stdout, end='')\n"
            "    if os.environ['LAB_MARKER'] in result.stdout:\n"
            f"        Path({str(proof)!r}).write_text('seen', encoding='utf-8')\n"
            "raise SystemExit(3)\n", encoding="utf-8")
        with patch.object(replay, "FROZEN", frozen):
            data = self.assert_private_replay("B1,B4")
        self.assertEqual(proof.read_text(encoding="utf-8"), "seen")
        self.assertTrue(data["rows"]["B4"])
        self.assertTrue(all(score["status"] != "NOT_RUN" for score in data["rows"]["B4"]))

    def test_timeout_marker_stays_private_and_lab_is_removed(self):
        frozen = self.copy_frozen()
        contract_path = frozen / "contracts.json"
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        contract["replay_cases"]["b1_cases"] = ["timeout"]
        for case in contract["replay_cases"]["cases"]:
            if case["id"] == "timeout":
                case["harness_wall_clock_s"] = 1.5
        contract_path.write_text(json.dumps(contract), encoding="utf-8")
        emitted = self.root / "emitted"
        completed = self.root / "completed"
        (self.package / "__main__.py").write_text(
            "import os, time\n"
            "from pathlib import Path\n"
            "print(os.environ['LAB_MARKER'], flush=True)\n"
            f"Path({str(emitted)!r}).touch()\n"
            "time.sleep(60)\n"
            f"Path({str(completed)!r}).touch()\n", encoding="utf-8")
        with patch.object(replay, "FROZEN", frozen):
            data = self.assert_private_replay("B1")
        score = data["rows"]["B1"][0]
        self.assertEqual(score["status"], "FAIL")
        self.assertTrue(score["observed"]["timed_out"])
        self.assertFalse(score["checks"]["ladder_must_stop_itself"])
        self.assertTrue(emitted.exists())
        self.assertFalse(completed.exists())
