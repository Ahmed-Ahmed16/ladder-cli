# ladder against the "Your Agent Hates Your CLI" checklist

Written 2026-11-15. Source talk: https://www.youtube.com/watch?v=rS36lYuvXQ8 (machine captions, some words wrong). Code lines refer to commit `4501630`. Installed `ladder` 0.1.0 matched this source; the installed skill copies match `src/ladder/skill/SKILL.md` byte for byte.

## Result per checklist item

| # | Item | Mark | Evidence |
| --- | --- | --- | --- |
| 1 | Fail loudly: last lines are a short summary plus a path to the full log | **missing** (partial) | Gates end with `FAIL step N of M ... (exit X)` on standard output (`src/ladder/gates.py:35`). A task ends with `ladder: step N of M failed (exit X)`, but on standard error (`src/ladder/tasks.py:28`). No full log file exists anywhere. A passing task prints no closing line. Ticket 08. |
| 2 | Pipefail traps | **missing** | `shell = "bash"` runs `bash -c <line>` with no `pipefail` (`src/ladder/tasks.py:9`). Lab: `python gen.py 2 5 \| cat` exits 0. Ticket 09. |
| 3 | Limits: "showing 20 of 300, add --offset 20" | **missing** | Task and gate output streams every line (`src/ladder/process.py:132`). `pr comments` reads `reviewThreads(first: 100)` and `comments(first: 50)` (`src/ladder/pr.py:10`, `:16`) and never says when more exist. It also hides resolved threads and cuts bodies with no hint about `--all` or `--full`. Tickets 11 and 12. |
| 4 | Compact output | **done** for core jobs | `pr comments` cuts each body to 3 plain lines and drops HTML and `<details>` (`src/ladder/pr.py:59-77`). `wait-review` prints only when its status line changes (`src/ladder/review.py:80`). `doctor` prints 1 line per check and 1 overall line (`src/ladder/cli.py:140`). Task output is the gap, covered by ticket 11. |
| 5 | Batch calls | **not needed now** | Gates already run all pre-commit steps in 1 call (`src/ladder/gates.py:23`), and a task `run` list runs several steps in 1 call (`src/ladder/tasks.py:25`). The transcripts show no loop over ladder calls. Add a batch job only when a replay (ticket 14b) shows agents looping over ladder. |
| 6 | Agent mode when `CLAUDECODE` is set | **missing** | No source line reads `CLAUDECODE`; the only environment reads are `LADDER_DEBUG`, `LADDER_BASH`, `PATH` and `SystemRoot`. `CLAUDECODE=1` was set in this Claude Code session. Ticket 10. |
| 7 | Skill and help text are the interface; stale text is a bug | **missing** (stale text found) | The help description lists `help \| list \| doctor \| pr comments \| pr wait-review \| add \| <task> [args]` and leaves out `gates`, `init` and `install-skill` (`src/ladder/cli.py:61`). `ladder gates` in a repo with no `ladder.toml` says `no [gates] in ladder.toml` (`src/ladder/cli.py:170`). No test ties the skill page to the parser. Ticket 13. |
| 8 | Transcripts as a replay test set | **missing** | Tests use a fake runner only. No replay of real calls exists. Tickets 14 and 14b. |

## Lab run (2026-11-15)

A throwaway git repo in the session scratch folder held `gen.py` (print N lines, optional first line, then exit with a given code) and this `ladder.toml`:

```toml
[tasks.fail]
about = "Print 3 lines, then exit 3"
run = "python gen.py 3 3"

[tasks.long]
about = "Print 300 lines, then exit 0"
run = "python gen.py 300 0"

[tasks.longfail]
about = "Print the error first, then 300 lines, then exit 1"
run = "python gen.py 300 1 ERROR-database-not-found"

[tasks.pipe]
about = "A failed command piped into cat"
shell = "bash"
run = "python gen.py 2 5 | cat"

[tasks.multi]
about = "2 steps, the 2nd fails"
run = ["python gen.py 1 0", "python gen.py 2 4"]

[gates]
run = ["python gen.py 2 0", "python gen.py 300 2 ERROR-lint-failed", "python gen.py 1 0"]
```

Each run used PowerShell 7 with `ladder <task> *> file` (all streams to 1 file). `<lab>` stands for the lab folder path.

| Run | Exit | Lines | Last line in the file |
| --- | --- | --- | --- |
| `ladder fail` | 3 | 6 | `ladder: step 1 of 1 failed (exit 3)` |
| `ladder long` | 0 | 302 | `line 300 of 300` (no closing line) |
| `ladder longfail` | 1 | 304 | `line 300 of 300`. The failure line sat at line 138 of 304. |
| `ladder pipe` | **0** | 4 | `line 2 of 2`. The command exited 5; ladder reported success. |
| `ladder multi` | 4 | 7 | `ladder: step 2 of 2 failed (exit 4)` |
| `ladder gates` | 2 | 308 | `FAIL step 2 of 3: python gen.py 300 2 ERROR-lint-failed (exit 2)` |
| `ladder gates --dry-run` | 0 | 4 | `3: python gen.py 1 0` |
| `ladder nosuch` | 1 | 1 | `ladder: unknown job or task "nosuch"; run ladder list` |

Notes:

* The `longfail` failure line went to standard error. PowerShell reads both streams at the same time, so the line landed in the middle of the file. In Git Bash with `2>&1 | tail -3` it came last. An agent that reads the end of a PowerShell capture misses it.
* In `longfail` and `gates` the real error (`ERROR-...`) was the 1st line of the child output, about 300 lines above the end. `tail` alone never shows it.
* Every task run starts with `ladder: using <lab>\ladder.toml`, about 140 characters, on standard error.

## Pipe tax from real transcripts (crude)

`research/transcript-audit-2026-11-15.md` in the DevOps repo did not exist when this was written, so these are a hand count, not audit numbers. Source: Bash and PowerShell tool calls in `~/.claude/projects/*.jsonl` that run `ladder`, with copied sessions counted once.

* About 23 distinct ladder calls in about 16 transcript files. `___` exact: 6 calls were cut by an escaped quote, so what came after them is unknown.
* 7 of 23 (about 30%) were piped into `head`, `tail` or `grep`, or written to a file that was then read with `tail` or `grep`.
* Both real `ladder gates` runs were written to a file, then read with `tail -15` or `grep`. That is the agent building its own "full log plus short end" by hand.
* 4 calls added `echo exit=$?` after ladder.
* 0 calls used `pr comments` or `pr wait-review`.
* In 1 company repo's `ladder.toml`, 4 tasks use `shell = "bash"`; none of them pipes at the top level today.

## Ranking

1. **08 fail loudly.** Every gates run in the transcripts rebuilt this by hand, and the lab lost the failure line in a PowerShell capture.
2. **09 pipefail.** Proven false pass in the lab. About 10 changed lines. No real task pipes today, so the harm is waiting, not current.
3. **10 then 11, agent mode and output cap.** 5 of 23 calls cut ladder output with `head` or `tail`. Needs 08 first.
4. **13 help and skill drift.** Stale help text exists today. Small.
5. **12 pr comments limits.** Real gap, but 0 uses in the transcripts.
6. **14 and 14b replay set.** Makes later changes measurable. Only about 23 calls exist so far, so it pays off later.
