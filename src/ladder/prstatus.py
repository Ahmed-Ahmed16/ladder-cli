import io
import json
import re

from .pr import field, text
from .process import LadderError, plain


FIELDS = ("number,url,state,title,headRefOid,reviewDecision,reviewRequests,"
          "latestReviews,statusCheckRollup")
FAILED = {"FAILURE", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE"}
PASSED = {"SUCCESS", "NEUTRAL", "SKIPPED"}
ERROR_LINE = re.compile(r"error|fail|exception|traceback|assert|panic", re.I)


def quiet_call(runner, operation, command):
    # This job returns only the result, including on API errors.
    previous = runner.out
    runner.out = io.StringIO()
    try:
        return getattr(runner, operation)(command)
    finally:
        runner.out = previous


def read_pr(number, runner):
    command = ["gh", "pr", "view"]
    if number is not None:
        command.append(str(number))
    answer = quiet_call(runner, "capture", [*command, "--json", FIELDS])
    try:
        pr = json.loads(answer)
    except json.JSONDecodeError as error:
        raise LadderError("gh returned bad PR JSON") from error
    if (type(field(pr, "number")) is not int or field(pr, "number") <= 0
            or not text(pr, "url") or not text(pr, "state")):
        raise LadderError("gh returned missing or invalid PR fields")
    return pr


def check_state(check):
    kind = text(check, "__typename")
    if kind not in ("", "CheckRun", "StatusContext"):
        return "pending"
    if kind == "StatusContext" or (not kind and text(check, "context")):
        if not text(check, "context"):
            return "pending"
        state = text(check, "state").upper()
        if state in {"FAILURE", "ERROR"}:
            return "failed"
        return "passed" if state == "SUCCESS" else "pending"
    conclusion = text(check, "conclusion").upper()
    if conclusion in FAILED:
        return "failed"
    if (text(check, "name") and text(check, "status").upper() == "COMPLETED"
            and conclusion in PASSED):
        return "passed"
    return "pending"


def check_summary(checks):
    if not checks:
        return "green: unknown; no checks reported"
    states = [check_state(check) for check in checks]
    failed, passed, pending = (states.count(state) for state in ("failed", "passed", "pending"))
    green = "no" if failed else ("unknown" if pending else "yes")
    return f"green: {green}; checks: {failed} failed, {passed} passed, {pending} pending"


def run_id(check):
    value = field(check, "checkSuite/workflowRun/databaseId")
    if type(value) is int and value > 0:
        return str(value)
    if isinstance(value, str) and re.fullmatch(r"[1-9][0-9]*", value):
        return value
    match = re.search(r"/runs/([1-9][0-9]*)(?:[/?#]|$)", text(check, "detailsUrl"))
    return match[1] if match else None


def read_log(identifier, runner):
    if identifier is None:
        return []
    try:
        code, answer = quiet_call(runner, "check", ["gh", "run", "view", identifier, "--log-failed"])
    except LadderError:
        return []
    if code or not answer.strip():
        return []
    return [plain(line) for line in answer.splitlines()]


def log_excerpt(lines, limit):
    if not any(lines):
        return ["  log not available"]
    start = next((i for i, line in enumerate(lines) if ERROR_LINE.search(line)), None)
    if start is None:
        start = next(i for i, line in enumerate(lines) if line)
    shown = lines[start:start + limit]
    result = ["  first error: " + shown[0], *("  " + line for line in shown[1:])]
    if start + len(shown) < len(lines):
        result.append(f"  showing {len(shown)} of {len(lines)} log lines, add --all")
    return result


def review_summary(pr):
    decision = text(pr, "reviewDecision") or "none"
    requests = field(pr, "reviewRequests")
    requests = requests if isinstance(requests, list) else []
    line = "review: " + decision.lower()
    if requests:
        names = [text(item, "login") or text(item, "name") or text(item, "slug") or "unknown"
                 for item in requests]
        return line + "; pending: " + ", ".join(names)
    if decision == "REVIEW_REQUIRED":
        return line + "; pending: requested"
    return line


def failure_lines(failed, limit, runner):
    for check in failed:
        identifier = run_id(check)
        name = text(check, "name") or text(check, "context") or "unknown"
        yield f"FAIL {name} (run {identifier or 'unknown'})"
        yield from log_excerpt(read_log(identifier, runner), limit)


def render_status(pr, args, runner):
    checks = field(pr, "statusCheckRollup")
    checks = [] if checks is None else (checks if isinstance(checks, list) else [None])
    failed = [check for check in checks if check_state(check) == "failed"]
    shown = failed if args.all else failed[:3]
    more = len(shown) < len(failed)
    # Reserve headers, review, and 1 cut marker per check within 25 lines.
    limit = 100 if args.all else min(10, (21 - len(shown) - int(more)) // max(1, len(shown)))
    lines = [f"PR #{pr['number']} {pr['state']}: {pr['url']}", check_summary(checks)]
    lines.extend(failure_lines(shown, limit, runner))
    if more:
        lines.append(f"showing {len(shown)} of {len(failed)} failed checks, add --all")
    lines.append(review_summary(pr))
    return lines


def status(args, runner, out):
    try:
        lines = render_status(read_pr(args.number, runner), args, runner)
    except LadderError as error:
        raise LadderError(plain(str(error))[:192]) from error
    for line in lines:
        # Sanitize before the cut so a secret cannot be exposed as a fragment.
        indent = "  " if line.startswith("  ") else ""
        print((indent + plain(line))[:200], file=out)
