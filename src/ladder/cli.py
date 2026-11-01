import argparse
from contextlib import redirect_stdout
import os
import sys
import time
import traceback

from .process import LadderError, Runner, plain, redact
from .pr import comments
from . import config
from .tasks import run_task
from .gates import run_gates, warn_ci
from .setup import init, install_skill
from .review import ReviewWait, review_logins


CORE_ABOUT = {
    "help": "show available commands",
    "list": "show core jobs and project tasks",
    "doctor": "check tools, sign in, Python, and ladder.toml",
    "pr": "read PR review threads or wait for reviews",
    "gates": "run project checks",
    "init": "create a project file",
    "install-skill": "install agent guidance",
}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise LadderError(message)


def pr_number(text):
    if not text.isascii() or not text.isdecimal() or not 0 < int(text) <= 2**32 - 1:
        raise argparse.ArgumentTypeError("PR number must be a positive 32 bit integer")
    return int(text)


def timeout_minutes(text):
    message = "must be a whole number >= 1"
    try:
        if text.isascii() and text.isdecimal() and int(text) >= 1:
            return int(text)
    except ValueError:
        pass
    raise argparse.ArgumentTypeError(message)


def reviewer_login(text):
    if not text.strip():
        raise argparse.ArgumentTypeError("must be a non empty login")
    return text.strip()


def arguments():
    parser = Parser(prog="ladder", description="help | list | doctor | pr comments | pr wait-review | <task> [args]")
    jobs = parser.add_subparsers(dest="job")
    jobs.add_parser("help", help="show available commands")
    jobs.add_parser("list", help=CORE_ABOUT["list"])
    jobs.add_parser("doctor", help="check git, gh, sign in, and Python")
    pr = jobs.add_parser("pr", help=CORE_ABOUT["pr"])
    commands = pr.add_subparsers(dest="command", required=True)
    comments = commands.add_parser("comments", help="show review threads")
    comments.add_argument("number", type=pr_number, metavar="PR number")
    comments.add_argument("--all", action="store_true", help="include resolved threads")
    comments.add_argument("--full", action="store_true", help="keep whole comment bodies")
    wait = commands.add_parser("wait-review", help="wait for reviews of the newest commit", allow_abbrev=False)
    wait.add_argument("number", type=pr_number, metavar="PR number")
    wait.add_argument("--bot", action="append", type=reviewer_login, metavar="LOGIN",
                      help="replace configured reviewers; may be repeated")
    wait.add_argument("--timeout-mins", type=timeout_minutes, default=20, metavar="N",
                      help="whole number >= 1 (default: 20)")
    gates = jobs.add_parser("gates", help=CORE_ABOUT["gates"], allow_abbrev=False)
    gates.add_argument("--dry-run", action="store_true", help="print steps without running them")
    for name in ("init", "install-skill"):
        jobs.add_parser(name, help=CORE_ABOUT[name])
    return parser


def check_version(runner, program):
    try:
        code, stdout = runner.check([program, "--version"])
    except LadderError as error:
        return 1, str(error)
    label = stdout.splitlines()[0] if code == 0 and stdout else f"{program}: exit {code}"
    return code, label


def config_check(load_config):
    try:
        project = load_config(os.getcwd())
    except (LadderError, NotImplementedError) as error:
        return 1, str(error)
    label = f"{project.path} ({len(project.tasks)} tasks)" if project is not None else "none in this repo"
    return 0, label


def list_jobs(project, out):
    width = max(map(len, config.CORE_JOBS))
    for name in config.CORE_JOBS:
        print(f"{name:<{width}}  {CORE_ABOUT[name]}", file=out)
    if project is None:
        print("no ladder.toml found", file=out)
        return
    print(f"Project tasks (from {plain(project.path)}):", file=out)
    width = max((len(plain(name)) for name in project.tasks), default=0)
    for task in project.tasks.values():
        suffix = " [needs --yes]" if task.confirm else ""
        print(f"{plain(task.name):<{width}}  {plain(task.about)}{suffix}", file=out)


def doctor(runner, out, load_config):
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
    code, label = config_check(load_config)
    failed += code != 0
    print(f"{'FAIL' if code else 'ok  '} ladder.toml: {plain(label)}", file=out)
    print(f"doctor: {failed} check(s) failed" if failed else "doctor: all checks passed", file=out)
    return int(failed != 0)


def main(argv, runner, out, err, load_config=config.load, *, home=None,
         clock=time.monotonic, sleep=time.sleep) -> int:
    try:
        if argv and argv[0] not in (*config.CORE_JOBS, "-h", "--help"):
            return run_task(load_config(os.getcwd()), argv, runner, err)
        parser = arguments()
        with redirect_stdout(out):
            args = parser.parse_args(argv)
        if args.job in (None, "help"):
            parser.print_help(out)
        elif args.job == "doctor":
            return doctor(runner, out, load_config)
        elif args.job == "list":
            list_jobs(load_config(os.getcwd()), out)
        elif args.job == "pr":
            if args.command == "comments":
                comments(args, runner, out)
            else:
                args.reviewers = review_logins(load_config(os.getcwd()), args.bot)
                ReviewWait(clock, sleep).wait(args, runner, out)
        elif args.job == "gates":
            project = load_config(os.getcwd())
            if project is None or not project.gates:
                raise LadderError("no [gates] in ladder.toml")
            print(f"ladder: using {plain(project.path)}", file=err, flush=True)
            warn_ci(project, err)
            return run_gates(args, project, runner, out)
        elif args.job == "init":
            init(os.getcwd(), out)
        elif args.job == "install-skill":
            install_skill(out, home)
        return 0
    except SystemExit as error:
        return error.code
    except LadderError as error:
        print(f"ladder: {plain(str(error))}", file=err)
        return 1
    except Exception as error:
        print(f"ladder: {plain(str(error)) or type(error).__name__}", file=err)
        if os.environ.get("LADDER_DEBUG") == "1":
            print(redact(traceback.format_exc()), file=err, end="")
        return 1


def run():
    sys.exit(main(sys.argv[1:], Runner(sys.stdout), sys.stdout, sys.stderr))
