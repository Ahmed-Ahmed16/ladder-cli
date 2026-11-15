import argparse
from contextlib import chdir
from datetime import datetime, timezone
import hashlib
import itertools
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

from .harness import make_lab, run_ladder
from .scoring import (build_verdict, extract_log_path, score_b3,
                      score_matrix_cell, score_pr_state, score_replay_case)


FROZEN = Path(__file__).resolve().parent
REPO = FROZEN.parents[1]


class UsageParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError("usage")


def not_run(case_id, reason):
    return {"id": case_id, "status": "NOT_RUN", "reason": reason}


def safe_case(case_id, action):
    try:
        return action()
    except Exception as error:
        return {"id": case_id, "status": "FAIL", "false_success": False,
                "checks": {}, "observed": {"error_class": type(error).__name__}}


def gh_shims(folder, script):
    folder.mkdir()
    (folder / "gh.cmd").write_text(f'@"{sys.executable}" "{script}" %*\n', encoding="utf-8")
    executable = folder / "gh"
    executable.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(script))} "$@"\n',
                          encoding="utf-8")
    executable.chmod(0o755)
    return {"PATH": str(folder) + os.pathsep + os.environ.get("PATH", "")}


def offline_gh(folder):
    script = folder / "offline_gh.py"
    script.write_text('import sys\n'
                      'if sys.argv[1:] == ["--version"]:\n'
                      '    print("gh frozen-offline")\n'
                      '    raise SystemExit(0)\n'
                      'raise SystemExit(1)\n', encoding="utf-8")
    return gh_shims(folder / "offline-bin", script)


def b1_case(build_src, spec, control, offline_env):
    with tempfile.TemporaryDirectory(prefix="ladder-b1-") as scratch:
        lab = make_lab(Path(scratch) / "lab")
        env = dict(offline_env)
        argv = list(spec["argv"])
        if spec["id"] == "timeout":
            env.update(control["env"])
            argv.extend(control["args"])
        remove = [name for name in ("CLAUDECODE", "LADDER_AGENT") if name not in env]
        result = run_ladder(build_src, argv, lab, env_set=env, env_remove=remove,
                            wall_clock_s=spec.get("harness_wall_clock_s", 60))
        with chdir(lab):
            return score_replay_case(spec, result)


def matrix_cells(contract):
    axes = contract["matrix"]["axes"]
    for values in itertools.product(*(axes[key] for key in ("tty", "claudecode", "override"))):
        cell = dict(zip(("tty", "claudecode", "override"), values))
        cell["id"] = ",".join(f"{key}={value}" for key, value in cell.items())
        yield cell


def matrix_case(build_src, cell, offline_env):
    launcher = FROZEN / "tty_launcher.py" if cell["tty"] == "yes" else None
    with tempfile.TemporaryDirectory(prefix="ladder-b2-") as scratch:
        lab = make_lab(Path(scratch) / "lab")
        env = dict(offline_env)
        remove = []
        if cell["claudecode"] == "set":
            env["CLAUDECODE"] = "1"
        else:
            remove.append("CLAUDECODE")
        if cell["override"] == "none":
            remove.append("LADDER_AGENT")
        else:
            env["LADDER_AGENT"] = cell["override"].split("=", 1)[1]
        doctor = run_ladder(build_src, ["doctor"], lab, env_set=env, env_remove=remove,
                            launcher=launcher)
        dryrun = run_ladder(build_src, ["gates", "--dry-run"], lab,
                            env_set=env, env_remove=remove, launcher=launcher)
        return score_matrix_cell(cell, doctor, dryrun)


def b3_case(build_src, spec, offline_env):
    with tempfile.TemporaryDirectory(prefix="ladder-b3-") as scratch:
        lab = make_lab(Path(scratch) / "lab")
        env = dict(offline_env, LADDER_AGENT="1")
        result = run_ladder(build_src, [spec["case"]], lab, env_set=env,
                            env_remove=("CLAUDECODE",))
        log_result = None
        with chdir(lab):
            log_path = extract_log_path(result.lines)
            if "log_read" in spec and log_path is not None:
                read = spec["log_read"]
                argv = [part.format(log=str(log_path), pattern=read["pattern"])
                        for part in read["argv_template"]]
                log_result = run_ladder(build_src, argv, lab, env_set=env,
                                        env_remove=("CLAUDECODE",))
            return score_b3(spec, result, log_result)


def pr_case(build_src, state_id, spec, shim_env):
    with tempfile.TemporaryDirectory(prefix="ladder-b4-") as scratch:
        lab = make_lab(Path(scratch) / "lab")
        env = dict(shim_env, FAKE_GH_STATE=str(FROZEN / "pr_states" / f"{state_id}.json"))
        result = run_ladder(build_src, ["pr", "status"], lab, env_set=env,
                            env_remove=("CLAUDECODE", "LADDER_AGENT"))
        return score_pr_state(state_id, spec, result)


def replay_rows(build_src, selected, contract):
    rows = {}
    cases = {spec["id"]: spec for spec in contract["replay_cases"]["cases"]}
    with tempfile.TemporaryDirectory(prefix="ladder-replay-") as scratch:
        scratch = Path(scratch)
        offline_env = offline_gh(scratch)
        for row in dict.fromkeys(selected):
            if row == "B1":
                control = contract["replay_cases"]["timeout_control"]
                rows[row] = [safe_case(case_id, lambda s=cases[case_id]:
                             b1_case(build_src, s, control, offline_env))
                             for case_id in contract["replay_cases"]["b1_cases"]]
            elif row == "B2":
                rows[row] = [safe_case(cell["id"], lambda c=cell:
                             matrix_case(build_src, c, offline_env))
                             for cell in matrix_cells(contract)]
            elif row == "B3":
                specs = contract["builds"]["B3a_B3b"]["replay"].values()
                rows[row] = [safe_case(spec["case"], lambda s=spec:
                             b3_case(build_src, s, offline_env)) for spec in specs]
            elif row == "B4":
                specs = contract["pr_replay"]["per_state"]
                if not (FROZEN / "fake_gh.py").is_file() or not (FROZEN / "pr_states").is_dir():
                    rows[row] = [not_run(state, "fake_gh_missing") for state in specs]
                else:
                    shim_env = gh_shims(scratch / "pr-bin", FROZEN / "fake_gh.py")
                    rows[row] = [safe_case(state, lambda i=state, s=spec:
                                 pr_case(build_src, i, s, shim_env)) for state, spec in specs.items()]
    rows["B5"] = {"status": "NOT_RUN", "reason": "not_built_before_b5"}
    rows["agent_questions"] = {name: {"status": "NOT_RUN", "reason": "no_live_agent_run_in_b0"}
                               for name in contract["questions"]}
    return rows


def metadata(build_src, label, contract_bytes):
    tree = subprocess.run(["git", "rev-parse", "HEAD:src"], cwd=REPO,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, encoding="utf-8", errors="replace", check=False)
    tree_hash = tree.stdout.strip() if tree.returncode == 0 else "___"
    return {"label": label, "date": datetime.now(timezone.utc).date().isoformat(),
            "python_version": ".".join(map(str, sys.version_info[:3])),
            "src_tree_hash": tree_hash, "build_src": build_src.name,
            "contracts_sha256": hashlib.sha256(contract_bytes).hexdigest()}


def verdicts(rows):
    result = {}
    all_scores = []
    for row, cases in rows.items():
        if isinstance(cases, list):
            required = list(cases)
            if row == "B2":
                required.extend(rows.get("B1", [not_run("B1", "b1_not_requested")]))
            result[row] = build_verdict(required)
            all_scores.extend(cases)
        elif row == "agent_questions":
            all_scores.extend(cases.values())
        else:
            result[row] = build_verdict([cases])
            all_scores.append(cases)
    result["overall"] = build_verdict(all_scores)
    return result


def markdown(data):
    lines = ["| Row | Case | Status | False success | Reason |",
             "| --- | --- | --- | --- | --- |"]
    for row, cases in data["rows"].items():
        if isinstance(cases, dict):
            cases = ([dict(id=row, **cases)] if "status" in cases else
                     [dict(id=name, **score) for name, score in cases.items()])
        for case in cases:
            lines.append(f"| {row} | {case['id']} | {case['status']} | "
                         f"{int(case.get('false_success', False))} | {case.get('reason', '')} |")
    lines.extend(["", "| Row | Pass | Fail | Not run | False success |",
                  "| --- | --- | --- | --- | --- |"])
    for row, verdict in data["verdicts"].items():
        lines.append(f"| {row} | {verdict['pass_count']} | {verdict['fail_count']} | "
                     f"{verdict['not_run_count']} | {verdict['false_success_count']} |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = UsageParser(description="Score a ladder source build against the frozen contract.")
    parser.add_argument("--build-src", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--md", type=Path)
    parser.add_argument("--only", default="B1,B2,B3,B4")
    try:
        args = parser.parse_args(argv)
        selected = list(dict.fromkeys(args.only.split(",")))
        if not selected or any(row not in ("B1", "B2", "B3", "B4") for row in selected):
            return 2
        build_src = args.build_src.resolve()
        if not (build_src / "ladder").is_dir():
            return 2
        contract_bytes = (FROZEN / "contracts.json").read_bytes()
        contract = json.loads(contract_bytes)
        rows = replay_rows(build_src, selected, contract)
        data = {"meta": metadata(build_src, args.label, contract_bytes),
                "rows": rows, "verdicts": verdicts(rows)}
        args.out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        if args.md is not None:
            args.md.write_text(markdown(data), encoding="utf-8")
        return 0
    except (KeyError, TypeError) as error:
        sys.stderr.write(type(error).__name__ + "\n")
        return 2
    except (ValueError, OSError):
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
