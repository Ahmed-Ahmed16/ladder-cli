"""Score merged CLI output against the frozen contract without running commands."""

import re
from pathlib import Path


_CUT = re.compile(r"(showing \d+ of \d+|\d+ lines cut)")
_PR_FAILED_CHECKS = {"pr-one-failed": "unit-tests", "pr-log-missing": "lint"}


def _nonempty(lines):
    return [line.strip() for line in lines if line.strip()]


def last_line_class(line):
    """Return a fixed label. Never retain child text in a score."""
    line = line.strip()
    if not line:
        return "empty"
    if re.search(r"\bFAIL\b", line):
        return "fail_line"
    if line.startswith(("ladder: ok", "gates: all")) or re.search(r"\bPASS\b", line):
        return "ok_line"
    if _CUT.search(line):
        return "cut_line"
    return "child_line"


def extract_log_path(lines):
    """Return the existing .log path named in the last 3 nonempty lines, or None."""
    for line in reversed(_nonempty(lines)[-3:]):
        for end in reversed(list(re.finditer(r"\.log(?=$|[\s\"'`),;\]])", line, re.I))):
            prefix = line[:end.end()]
            starts = [0] + [match.end() for match in re.finditer(r"[\s\"'`=:(\[]", prefix)]
            for start in starts:
                candidate = prefix[start:].strip()
                if not candidate:
                    continue
                try:
                    if Path(candidate).is_file():
                        return Path(candidate)
                except (OSError, ValueError):
                    continue
    return None


def _observed(result):
    lines = _nonempty(result.lines)
    return {
        "exit_code": result.exit_code,
        "line_count": len(result.lines),
        "last_line_class": last_line_class(lines[-1] if lines else ""),
        "timed_out": bool(result.timed_out),
    }


def _score(result, checks, false_success=False, **extra):
    return {
        "status": "PASS" if all(checks.values()) and not false_success else "FAIL",
        "false_success": bool(false_success),
        "checks": checks,
        "observed": _observed(result),
        **extra,
    }


def _exit_matches(expected, exit_code):
    return exit_code != 0 if expected == "nonzero" else exit_code == expected


def score_replay_case(spec, result):
    lines = _nonempty(result.lines)
    last3 = lines[-3:]
    checks = {
        "not_timed_out": not result.timed_out,
        "exit": _exit_matches(spec["expect_exit"], result.exit_code),
    }
    if "expect_lines" in spec:
        ignored = tuple(spec.get("ignore_line_prefixes", ()))
        counted = [line for line in result.lines if not line.startswith(ignored)]
        checks["line_count"] = len(counted) == spec["expect_lines"]
    if "expect_text" in spec:
        checks["text"] = any(spec["expect_text"] in line for line in result.lines)
    if "last3_contains_word" in spec:
        word = re.escape(spec["last3_contains_word"])
        checks["last3_word"] = any(re.search(r"\b" + word + r"\b", line, re.I) is not None for line in last3)
    if spec.get("ladder_must_stop_itself"):
        checks["ladder_must_stop_itself"] = not result.timed_out
    log_path = extract_log_path(result.lines)
    no_fail_summary = spec.get("no_fail_summary", bool(
        spec.get("must_fail") and "expect_text" in spec and "expect_lines" in spec))
    if spec.get("must_fail") and not no_fail_summary:
        checks["fail_summary"] = any(re.search(r"\bFAIL\b", line) is not None for line in last3)
        checks["log_path"] = log_path is not None
    if "log_contains" in spec:
        try:
            checks["log_contains"] = log_path is not None and spec["log_contains"] in Path(log_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            checks["log_contains"] = False
    false_success = bool(
        not result.timed_out and spec.get("must_fail")
        and (result.exit_code == 0 or last_line_class(lines[-1] if lines else "") == "ok_line")
    )
    return _score(result, checks, false_success, id=spec["id"])


def expected_mode(cell):
    override = cell["override"]
    if override == "LADDER_AGENT=1":
        return "agent"
    if override == "LADDER_AGENT=0":
        return "human"
    return "agent" if cell["claudecode"] == "set" and cell["tty"] == "no" else "human"


def score_matrix_cell(cell, doctor_result, dryrun_result):
    cell_id = cell.get("id", ",".join(key + "=" + cell[key] for key in ("tty", "claudecode", "override")))
    mode = expected_mode(cell)
    checks = {
        "not_timed_out": not doctor_result.timed_out and not dryrun_result.timed_out,
        "mode_line": any(line.startswith("ok   mode: " + mode) for line in doctor_result.lines),
        "using_line": any(line.startswith("ladder: using ") for line in dryrun_result.lines) == (mode == "human"),
    }
    method = "injected_isatty" if cell["tty"] == "yes" else "real_pipe"
    return _score(doctor_result, checks, id=cell_id, tty_method=method)


def score_b3(spec, result, log_result=None):
    """Score B3 output and, when supplied, the separate ladder log result."""
    replay_spec = {"id": spec["case"], "expect_exit": 0 if spec["case"] == "long" else 1,
                   "must_fail": spec["case"] != "long"}
    if "log_read" in spec:
        replay_spec["log_contains"] = spec["log_read"]["pattern"]
    score = score_replay_case(replay_spec, result)
    checks = score["checks"]
    checks["line_cap"] = len(result.lines) <= spec["max_total_lines"]
    cut_lines = [line for line in result.lines if re.search(spec.get("cut_line_regex", _CUT.pattern), line)]
    if spec.get("needs_cut_line"):
        checks["cut_line"] = bool(cut_lines)
    if spec.get("cut_line_names_log_path"):
        checks["cut_log_path"] = any(extract_log_path([line]) is not None for line in cut_lines)
    reason = None
    if "log_read" in spec:
        log_spec = spec["log_read"]
        checks["log_path"] = extract_log_path(result.lines) is not None
        if not checks["log_path"]:
            reason = "no_log_path"
        elif log_result is None:
            reason = "no_log_result"
        checks["log_result"] = log_result is not None
        if log_result is not None:
            checks.update({
                "log_not_timed_out": not log_result.timed_out,
                "log_exit": _exit_matches(log_spec["exit"], log_result.exit_code),
                "log_contains_result": any(log_spec["result_contains"] in line for line in log_result.lines),
                "log_line_cap": len(log_result.lines) <= log_spec["max_lines"],
            })
    score["status"] = "PASS" if all(checks.values()) and not score["false_success"] else "FAIL"
    if reason:
        score["reason"] = reason
    return score


def score_pr_state(state_id, spec, result):
    output = "\n".join(result.lines).lower()
    failed_check = _PR_FAILED_CHECKS.get(state_id)
    false_success = not result.timed_out and result.exit_code == 0 and (
        state_id == "pr-api-error"
        or (failed_check is not None and failed_check.lower() not in output)
    )
    checks = {
        "not_timed_out": not result.timed_out,
        "exit": _exit_matches(spec["expect_exit"], result.exit_code),
    }
    for index, text in enumerate(spec.get("must_contain", [])):
        checks["contains_" + str(index)] = text.lower() in output
    if spec.get("must_not_be_empty"):
        checks["not_empty"] = bool(output.strip())
    if "max_lines" in spec:
        checks["line_cap"] = len(result.lines) <= spec["max_lines"]
    return _score(result, checks, false_success, id=state_id)


def build_verdict(scores):
    """A pass allows NOT_RUN scores only when their reason is no_pty."""
    scores = list(scores.values() if isinstance(scores, dict) else scores)
    passed = sum(score["status"] == "PASS" for score in scores)
    failed = sum(score["status"] == "FAIL" for score in scores)
    unrun = sum(score["status"] == "NOT_RUN" for score in scores)
    false_success = sum(bool(score.get("false_success")) for score in scores)
    unexpected_unrun = any(score["status"] == "NOT_RUN" and score.get("reason") != "no_pty" for score in scores)
    return {
        "pass": failed == 0 and false_success == 0 and not unexpected_unrun,
        "pass_count": passed,
        "fail_count": failed,
        "not_run_count": unrun,
        "false_success_count": false_success,
    }
