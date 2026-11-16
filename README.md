# ladder

Ladder runs common project jobs from 1 command.
It reads PR review threads and checks the tools it needs.

Requires Python 3.12 or newer. It has no runtime packages to install.
PR commands need `gh` on PATH, with `gh` signed in.
`doctor` checks both `git` and `gh`.

Install from GitHub:

```console
pip install git+https://github.com/Ahmed-Ahmed16/ladder-cli
```

For local work, run this from the repo root:

```console
pip install -e .
```

Commands:

```console
ladder help
ladder list
ladder doctor
ladder pr status
ladder pr comments 82
ladder pr wait-review 82
ladder gates --dry-run
ladder gates
ladder add test --about "Run the tests" --run "python -m unittest discover -s tests -t ."
ladder init
ladder install-skill
```

Add `--all` to include resolved threads. Add `--full` for whole comment bodies.
The default shows the first 3 plain lines of each comment.
`python -m ladder` accepts the same arguments.
If doctor reports `FAIL`, fix that check and run it again. A failed check exits 1.

Use `ladder pr status [PR number] [--all]` for checks, first errors, and requested reviews.
The default uses the current branch and at most 25 lines; failed checks still exit 0.

Do not pipe capped output; read its last line or use `ladder log <name> --grep RE`.
Do not hand edit ladder.toml to add tasks; use `ladder add`.
Do not treat `ladder gates --dry-run` as a pass; it runs nothing. Run `ladder gates`.

### ladder.toml

Put project tasks in `ladder.toml` at the repo root.
Ladder finds the nearest parent folder with a `.git` file or folder.
It reads only that root's `ladder.toml`. Subfolder files are ignored.
Outside a git repo, ladder reads no config, even if a parent has one.

Add tasks with `ladder add`; never hand edit the file to add a task:

```console
ladder add test --about "Run the tests" --run "python -m unittest discover -s tests -t ."
ladder test
```

The added block looks like this:

```toml
[tasks.test]
about = "Run the tests"
run = "python -m unittest discover -s tests -t ."
```

`ladder list` shows tasks. `ladder test` runs this task from the file's folder.
Extra arguments pass through when `run` has 1 command.
Set `confirm = true` to require `--yes` before a task runs.
With 1 command, `--yes` also passes through to that command.
With several commands, ladder accepts `--yes` and keeps it out of every step.
Other extra arguments are refused for tasks with several commands.

`ladder add NAME --about TEXT --run LINE [--run LINE ...] [--shell bash] [--confirm]`
creates the root file when missing. Repeat `--run` to save a list of steps in order.
`--shell bash` and `--confirm` save those task settings only when given.
Names use ASCII letters, digits, `-` and `_` only. Core job names, including `add`, are reserved.
Ladder checks the whole new file before writing and preserves the existing bytes.
Bad names, invalid config, and use outside a git repo exit 1 without changing the file.
An existing task refuses with `task "NAME" already exists; edit its script instead`.
Fix that script in place, then run `ladder NAME` again.

Add the repo's checks in a `[gates]` block:

```toml
[gates]
run = ["python -m unittest discover -s tests -t ."]
```

`ladder gates` stops on failure and prints PASS or FAIL for each step.
`--dry-run` prints the steps without running them.
In human mode, tasks and gates print `ladder: using <path>` to standard error before the steps.
Dry runs print this line in human mode too. Exit 0 means success.
Failed steps return their exit code; input errors exit 1.

Every task and gates run (not `--dry-run`) writes its whole output to
`<temp folder>/ladder/logs/<task or gates>-<YYYYMMDD-HHMMSS>.log` and ends with a summary line
on standard output. The last line is the result and names the full log. Do not pipe ladder into `head` or `tail`.

```text
ladder: FAIL test, step 1 of 1, exit 3; full log: /tmp/ladder/logs/test-20261115-101500.log
ladder: ok test, 2 steps; full log: /tmp/ladder/logs/test-20261115-101530.log
FAIL step 2 of 3: python -m unittest (exit 2); full log: /tmp/ladder/logs/gates-20261115-101600.log
gates: all 3 passed; full log: /tmp/ladder/logs/gates-20261115-101700.log
```

Read a log with `ladder log gates --grep FAIL`, or pass the full path from the summary.
Use `--head N` or `--tail N`; the default shows the last 40 lines or regex matches.
Each line has at most 300 characters; `--max-chars N` caps log text (default: 4000).
The log holds all output, after secrets are redacted.
On Linux and macOS the log folder must be a real folder that you own and nobody else can open,
and each log file is created for you alone. Ladder refuses a link or a shared folder with an error.
Set `LADDER_TIMEOUT=<seconds>` to stop any step that runs longer. The summary then says
`timeout after <N>s (exit 124)`.

Tasks with `shell = "bash"` run as `bash -o pipefail -c <line>`. A failed command before a pipe
fails the task. A task that pipes into `head` can now fail with exit 141 when the reader closes early.

### Agent mode

Agent mode is on when `CLAUDECODE` is non-empty and stdout is not a terminal.
Set `LADDER_AGENT=0` or put `--human` first for full human output.
Set `LADDER_AGENT=1` to force agent mode.
Agent mode drops the `ladder: using <path>` line, including dry runs.
`ladder doctor` shows the mode and the config path.
Example: `ladder doctor` prints `ok   mode: agent (CLAUDECODE set, no TTY)`.

Use `ladder --human gates` to show the full human output for 1 run.
Tasks and gates show the first 10 and last 30 lines in agent mode; 40 lines or fewer show in full.
A `showing 40 of M lines (N cut); full log: <path>` line marks the cut; `LADDER_AGENT=0` also shows all lines.

### Wait for reviews

Choose the GitHub logins to wait for:

```toml
[review]
wait_for = ["review-bot", "reviewer"]
```

Run `ladder pr wait-review 82`. A review must name the newest commit.
Any review state except `PENDING` counts, including `CHANGES_REQUESTED`.
Login matching ignores case. This checks that a review was posted, not that it approved the PR.
Use `--bot reviewer` to replace the config list. Repeat `--bot` to wait for several logins.
Set `--timeout-mins N` to a whole number >= 1. The default is 20 min.

Ladder polls every 30 s. Status lines show the first 7 characters of the commit:

```text
abcdef0: waiting for review-bot, reviewer
abcdef0: waiting for reviewer
abcdef0: done: review-bot (COMMENTED), reviewer (APPROVED)
```

Status lines appear only when the state changes. A new commit gets a `head changed:` line,
and ladder checks reviews for that commit. All reviewers done exits 0.
Timeout exits 1 and names the logins still missing and the commit.
An empty or missing list stops without polling:

```text
ladder: no reviewer set: add [review] wait_for = ["login"] to ladder.toml or pass --bot
```

### Set up a repo and agents

Run `ladder init` from anywhere inside a git repo.
It creates `ladder.toml` at the root with a commented example task.
The starter gates run `git --version`; replace this with your CI steps.
If the file exists, ladder refuses: `ladder.toml already exists; edit it instead`.
It prints 2 lines to add to the repo's `AGENTS.md`. It does not edit that file.

Run `ladder install-skill` to install the packaged agent page in both:

* `~/.claude/skills/ladder/SKILL.md`
* `~/.agents/skills/ladder/SKILL.md`

It also adds guidance to `~/.codex/AGENTS.md`, between
`<!-- ladder:start -->` and `<!-- ladder:end -->`.
Reruns replace that section and preserve everything outside it.
Unpaired, repeated or reversed markers cause an error before any file changes.
If neither marker exists, ladder appends the section.
Each file gets a `wrote`, `updated` or `unchanged` line.
Unchanged files are left alone.
`ladder doctor` warns when an installed skill page differs from the packaged page.
Run `ladder install-skill` to update it. A stale page does not change the doctor exit code.

Before writing any script, run `ladder list`. Use a task that exists.
If a task is broken or outdated, fix its script in place. Never write a second script for the same job.
A script used once may stay in a temp folder.
Save a script the job will need again in `scripts/ladder/` in the repo.
Run `ladder add <name> --about "..." --run "..."`, then `ladder <name>` once to prove it works.
Put the script and the ladder.toml change in the same commit as the work.
In company repos, the task reaches Ahmed through the same PR.
Never hand edit ladder.toml to add a task. Never put a path outside the repo in its ladder.toml.
Personal scripts get tasks in their own folder's ladder.toml.
`needs --yes` means ask the human first. Agents must never add `--yes` on their own.

Run tests from the repo root. No install or GitHub access is needed:

```console
python -m unittest discover -s tests -t .
```

Plain `python -m unittest discover` also works.
