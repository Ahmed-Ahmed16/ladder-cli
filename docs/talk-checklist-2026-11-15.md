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

## Ranking with audit numbers (2026-11-15)

Source: `research/transcript-audit-2026-11-15.md` and `research/transcript-audit-2026-11-15.json` in the DevOps repo. These numbers replace the hand count of 23 calls for this ranking.

Scope of the numbers:

* Ladder calls: 536 in all. 103 are Claude calls and 433 are Codex calls. In the post-ladder window (2026-11-11 to 2026-11-15) there are 76.
* Pipe rate on ladder, Claude, all time: 46 of 103 calls (45%) went into `tail`, `head`, `grep`, `Select-Object`, `sed` or `Select-String`. The Codex split is not counted here.
* "all" means Claude, all time, from the audit JSON. "w_1029" means 2026-09-29 to 2026-10-29. "post" means 2026-11-11 to 2026-11-15.
* "at least" means the sum of the pipe pairs listed in the JSON. Other pairs may exist.

### Ranked tickets

| Rank | Ticket | Fixes | Audit number it rests on |
| --- | --- | --- | --- |
| 1 | 08 fail loudly, summary last | The agent pipes ladder output into `head` or `tail` to find the result. | 46 of 103 ladder calls piped (45%, all). 76 ladder calls (post). Also 845 exit-code failures (w_1029) and 106 (post). |
| 2 | 10 agent mode switch | Lets ticket 11 cut output for agents only. Build it first. | Same 46 of 103 (all). This ticket changes no output by itself. |
| 3 | 11 output cap in agent mode | Shows the first 10 and last 30 lines, with a marker and the log path. | Same 46 of 103 (all): tail 18, Select-Object 12, head 10, grep 4, sed 1, Select-String 1. |
| 4 | 15 `ladder pr status` (new) | Gives one short PR status, so agents do not pipe `gh` reads. | At least 1938 of 3825 `gh` calls piped (51%, all). |
| 5 | 14 replay runner | Measures the piped rate and the output change for each build. | Baseline: 46 of 103 (all) and 76 (post). This ticket adds no count of its own. |
| 6 | 14b extract calls | Writes the real calls file that ticket 14 replays. | The audit miner already reads the same ladder calls (46 of 103, all). Keep only the calls-file output, and reuse `scripts/ladder/transcript-audit.mjs` for parsing. |
| 7 | 09 pipefail | Stops a false pass: lab `exit 5 \| cat` gave exit 0. | No audit count. Pipes inside ladder tasks were not counted. Severity high, frequency `___`. |
| 8 | 13 help and skill drift | Stale help text and the gates message with no `ladder.toml`. | No audit count. Ladder ran 76 calls in the post window against 745 git calls. See the addendum on the skill text. |
| 9 | 12 pr comments limits | Hides threads and cuts bodies with no note. | No audit count. The hand count found 0 `pr comments` calls in 23. Check whether ticket 15 covers the same reads before building. |

### Addenda to existing tickets

These are text changes for the tickets. The ticket files are not changed yet.

* 08: add a timeout case. A task that times out ends with the same FAIL line, and the line says `timeout`. Audit: `timeout` 281 (w_1029) and 74 (post). The pair "timeout, then the same tool again" is 266 (all).
* 13: the skill trigger text names the 3 most common uses: gates before a commit, PR comments, and the repo tests. Audit: 76 ladder calls (post) against 745 git calls (post).

### New ticket

* 15 `ladder pr status`. File: `.scratch/ladder/issues/15-pr-status.md`. Rests on 1938 `gh` pipe pairs (at least, all).

### Issues ladder cannot fix

These have no ticket. Each row names the owner.

| Issue | Audit number | Owner | Next step |
| --- | --- | --- | --- |
| `git` output piped into `head`, `grep`, `tail`, `wc`, `sed` | 5366 of 11191 (w_1029). 409 of 745 (post). | Rule text in `~/.claude/CLAUDE.md` and the project `AGENTS.md` files. | Ahmed chooses the wording. A ladder task for git reads is not planned: the calls are ad hoc. |
| `relay.mjs` output piped | at least 658 of 1350 (all) | The relay tool, outside ladder-cli. | Add a quiet or `--last N` flag there. |
| `run-tests.sh` output piped | at least 304 of 427 (all) | Each repo's test script. | Ladder helps only when the repo runs it as a ladder task, after tickets 08 and 11. |
| `papercut.py` output piped | at least 196 of 442 (all) | The work-brain papercut script. | Add a quiet mode there. |
| `mita.py` output piped | at least 45 of 67 (all) | The mita repo tool. | Its owner decides. |
| Same tool again after a failed call | top 3 recovery pairs: 951, 713, 579 (all) | Rule text, and papercut on the 2nd failure. | Rule: read the error, then change the approach. |
| Unclear error labels (`other`) | 1233 (w_1029). 123 (post). | DevOps audit miner. | A second pass to label them. `___` |
| Calls blocked by a hook | 636 (w_1029). 63 (post). | The hook authors. | Check that each hook message says what to do next. |
| File or path missing | 591 (w_1029). 54 (post). | Rule text on Windows paths. | `___` |
| Permission and sandbox errors | 471 (w_1029). 21 (post). | Codex brief text in `codex-delegate`. | Already a papercut from 2026-11-12. |
| Python throwaway commands | 4563 (w_1029). 177 (post). | Inline-code hook (exists) and ticket 07 (done). | Falling. No new work. |
| Long PowerShell scripts in one call | 257 (w_1029). 225 (post). Claude all time: 2009 `ps_long_script`. | Rule text: a script over about 10 lines goes to a file. | `ladder add` (ticket 07, done) covers the repeats. |

### Notes on the counts

* The detector limits in audit section 8 apply. `user_rejected` and `timeout` are broad matches.
* No hand check was done on the labels. `___`
* Only ladder calls are counted in the ranking. The other tools are listed only as owner notes.

