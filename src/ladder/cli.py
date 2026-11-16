import argparse
from contextlib import redirect_stdout
from dataclasses import dataclass, replace
import os
from pathlib import Path
import sys
import time
import traceback
from typing import Callable, TextIO

from .process import LadderError, Runner, plain, redact
from .pr import comments
from .prstatus import status
from .logread import add_arguments as log_arguments, log_job
from . import config
from .mode import agent_mode
from .tasks import run_task
from .gates import run_gates, warn_ci
from .setup import check_skills, init, install_skill
from .add import add_task
from .review import ReviewWait, review_logins


@dataclass(frozen=True)
class Context:
    runner: Runner
    out: TextIO
    err: TextIO
    load_config: Callable[[str], config.Config | None] = config.load
    home: Path | None = None
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    agent: bool = False
    mode_reason: str = "no agent signal"

    def project(self):
        return self.load_config(os.getcwd())


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise LadderError(message)


def pr_number(text):
    if not text.isascii() or not text.isdecimal() or not 0 < int(text) <= 2**32 - 1:
        raise argparse.ArgumentTypeError("PR number must be a positive 32 bit integer")
    return int(text)


def timeout_minutes(text):
    digit_limit = sys.get_int_max_str_digits()
    if (text.isascii() and text.isdecimal()
            and (digit_limit == 0 or len(text) <= digit_limit) and int(text) >= 1):
        return int(text)
    raise argparse.ArgumentTypeError("must be a whole number >= 1")


def reviewer_login(text):
    if not text.strip():
        raise argparse.ArgumentTypeError("must be a non empty login")
    return text.strip()


RESULT_HELP = """Tasks and gates write the full output to a log file and end with a summary line that names it:
  ladder: FAIL test, step 1 of 1, exit 3; full log: <path>
The last line is the result. Do not pipe ladder into tail or head.
ladder log <log> selects lines by regex, then --head N or --tail N (default: last 40).
ladder log accepts a private log path or name; --max-chars N caps log text (default: 4000).
Example: ladder log gates --grep FAIL
Example: ladder pr status (checks, first errors, and requested reviews)
LADDER_TIMEOUT=<seconds> stops a step that runs too long (exit 124).
Tasks with shell = "bash" run with pipefail.

Agent mode is on when CLAUDECODE is non-empty and stdout is not a terminal.
LADDER_AGENT=1 forces agent mode.
LADDER_AGENT=0 or a leading --human forces the full human output.
Agent mode does not print the ladder: using <path> line.
Agent mode shows the first 10 and last 30 task/gates lines, plus showing 40 of M lines.
That line names the full log; ladder --human or LADDER_AGENT=0 shows all lines.
ladder doctor shows the mode and the config path.
Example: ladder --human gates"""


def arguments():
    parser = Parser(prog="ladder", epilog=RESULT_HELP,
                    formatter_class=argparse.RawDescriptionHelpFormatter)
    jobs = parser.add_subparsers(dest="job")
    job_parsers = {name: jobs.add_parser(name, help=config.CORE_JOBS[name],
                                       allow_abbrev=name not in ("gates", "add", "log"))
                   for name in config.CORE_JOBS}
    log_arguments(job_parsers["log"], timeout_minutes)
    pr_commands = pr_arguments(job_parsers["pr"])
    job_parsers["gates"].add_argument("--dry-run", action="store_true",
                                     help="print steps without running them")
    add_arguments(job_parsers["add"])
    parser.description = " | ".join((*config.CORE_JOBS,
                                     *(f"pr {name}" for name in pr_commands), "<task> [args]"))
    return parser


def pr_arguments(parser):
    commands = parser.add_subparsers(dest="command", required=True)
    comments = commands.add_parser("comments", help="show review threads")
    comments.add_argument("number", type=pr_number, metavar="PR number")
    comments.add_argument("--all", action="store_true", help="include resolved threads")
    comments.add_argument("--full", action="store_true", help="keep whole comment bodies")
    status = commands.add_parser("status", help="show checks, first errors, and reviews", allow_abbrev=False)
    status.add_argument("number", nargs="?", type=pr_number, metavar="PR number")
    status.add_argument("--all", action="store_true", help="show all failures and up to 100 log lines each")
    wait = commands.add_parser("wait-review", help="wait for reviews of the newest commit", allow_abbrev=False)
    wait.add_argument("number", type=pr_number, metavar="PR number")
    wait.add_argument("--bot", action="append", type=reviewer_login, metavar="LOGIN",
                      help="replace configured reviewers; may be repeated")
    wait.add_argument("--timeout-mins", type=timeout_minutes, default=20, metavar="N",
                      help="whole number >= 1 (default: 20)")
    return commands.choices


def add_arguments(parser):
    parser.add_argument("name", help="letters, digits, - and _ only")
    parser.add_argument("--about", required=True, help="describe the task")
    parser.add_argument("--run", required=True, action="append", help="command to run; may be repeated")
    parser.add_argument("--shell", choices=("bash",), help="use bash for shell features")
    parser.add_argument("--confirm", action="store_true", help="require --yes to run this task")


def check_version(runner, program):
    try:
        code, stdout = runner.check([program, "--version"])
    except LadderError as error:
        return 1, str(error)
    label = stdout.splitlines()[0] if code == 0 and stdout else f"{program}: exit {code}"
    return code, label


def config_check(context):
    try:
        project = context.project()
    except LadderError as error:
        return 1, str(error)
    label = f"{project.path} ({len(project.tasks)} tasks)" if project is not None else "none in this repo"
    return 0, label


def list_jobs(project, out):
    width = max(map(len, config.CORE_JOBS))
    for name, about in config.CORE_JOBS.items():
        print(f"{name:<{width}}  {about}", file=out)
    if project is None:
        print("no ladder.toml found", file=out)
        return
    print(f"Project tasks (from {plain(project.path)}):", file=out)
    width = max((len(plain(name)) for name in project.tasks), default=0)
    for task in project.tasks.values():
        suffix = " [needs --yes]" if task.confirm else ""
        print(f"{plain(task.name):<{width}}  {plain(task.about)}{suffix}", file=out)


def doctor(context):
    runner, out = context.runner, context.out
    failed = 0
    for program in ("git", "gh"):
        code, label = check_version(runner, program)
        failed += code != 0
        print(f"{'FAIL' if code else 'ok  '} {plain(label)}", file=out)
    try:
        code, _ = runner.check(["gh", "auth", "status"])
    except LadderError:
        code = 1
    failed += code != 0
    print(f"{'FAIL' if code else 'ok  '} gh auth: {'not signed in' if code else 'signed in'}", file=out)
    old_python = sys.version_info[:2] < (3, 12)
    failed += old_python
    print(f"{'FAIL' if old_python else 'ok  '} Python {'.'.join(map(str, sys.version_info[:3]))}", file=out)
    code, label = config_check(context)
    failed += code != 0
    print(f"{'FAIL' if code else 'ok  '} ladder.toml: {plain(label)}", file=out)
    print(f"ok   mode: {'agent' if context.agent else 'human'} ({context.mode_reason})", file=out)
    check_skills(out, context.home)
    print(f"doctor: {failed} check(s) failed" if failed else "doctor: all checks passed", file=out)
    return int(failed != 0)


def help_job(args, context):
    arguments().print_help(context.out)
    return 0


def doctor_job(args, context):
    return doctor(context)


def list_job(args, context):
    list_jobs(context.project(), context.out)
    return 0


def pr_job(args, context):
    if args.command == "comments":
        comments(args, context.runner, context.out)
    elif args.command == "status":
        status(args, context.runner, context.out)
    else:
        args.reviewers = review_logins(context.project(), args.bot)
        ReviewWait(context.clock, context.sleep).wait(args, context.runner, context.out)
    return 0


def gates_job(args, context):
    project = context.project()
    if project is None:
        raise LadderError("no ladder.toml in this repo; run ladder init")
    if not project.gates:
        raise LadderError("no [gates] in ladder.toml")
    if not context.agent:
        print(f"ladder: using {plain(project.path)}", file=context.err, flush=True)
    warn_ci(project, context.err)
    return run_gates(args, project, context.runner, context.out, agent=context.agent)


def init_job(args, context):
    init(os.getcwd(), context.out)
    return 0


def add_job(args, context):
    add_task(os.getcwd(), args, context.out)
    return 0


def install_skill_job(args, context):
    install_skill(context.out, context.home)
    return 0


JOBS = {
    "help": help_job,
    "list": list_job,
    "doctor": doctor_job,
    "pr": pr_job,
    "gates": gates_job,
    "log": log_job,
    "add": add_job,
    "init": init_job,
    "install-skill": install_skill_job,
}


def main(argv, context) -> int:
    try:
        if argv[:1] == ["--human"]:
            argv = argv[1:]
            context = replace(context, agent=False, mode_reason="--human")
        if argv and argv[0] not in (*config.CORE_JOBS, "-h", "--help"):
            return run_task(context.project(), argv, context.runner, context.out, context.err,
                            announce=not context.agent, agent=context.agent)
        parser = arguments()
        with redirect_stdout(context.out):
            args = parser.parse_args(argv)
        return JOBS[args.job or "help"](args, context)
    except SystemExit as error:
        return error.code
    except LadderError as error:
        print(f"ladder: {plain(str(error))}", file=context.err)
        return 1
    except Exception as error:
        print(f"ladder: {plain(str(error)) or type(error).__name__}", file=context.err)
        if os.environ.get("LADDER_DEBUG") == "1":
            print(redact(traceback.format_exc()), file=context.err, end="")
        return 1


def run():
    agent, reason = agent_mode(os.environ, sys.stdout.isatty())
    context = Context(Runner(sys.stdout), sys.stdout, sys.stderr, agent=agent, mode_reason=reason)
    sys.exit(main(sys.argv[1:], context))
