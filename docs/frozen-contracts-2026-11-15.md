# Frozen test contracts for ladder builds B1 to B6b

Frozen 2026-11-15 by build session B0 (ladder-0). Source: the build plan `build-plan-2026-11-15.md` (DevOps repo, commit c1e5a5a), table "Frozen test contracts". This work is test code and docs only. No file under `src/` changed.

**Rule.** After B1 starts, nothing here changes. A change needs Ahmed's yes and a new dated addendum file. Two fields may be filled later, and only those: `replay_cases.timeout_control` (B1) and `builds.B3a_B3b.replay.longfail150_agent_mode.log_read.argv_template` (B3b). The commit must say so.

## Where things are

| Item | File |
| --- | --- |
| All contracts, expected answers, minimum scores, scoring rule | `tests/frozen/contracts.json` |
| Lab templates (`gen.py`, `ladder.toml`) | `tests/frozen/lab/` |
| Replay harness and scoring | `tests/frozen/harness.py`, `scoring.py`, `replay.py` |
| 6 fake PR states and the fake `gh` | `tests/frozen/pr_states/`, `tests/frozen/fake_gh.py` |
| Agent answer scorer (no live runs) | `tests/frozen/agent_questions.py` |
| Frozen Claude sample for B6 | `tests/frozen/claude_sample.json` |
| Pre-B1 scores | `docs/frozen-scores-pre-b1-2026-11-15.json` and `.md` |

Run the harness on any build (a `src` folder):

```console
python -m tests.frozen.replay --build-src src --label pre-b1 --out scores.json --md scores.md
```

The unit tests of the harness run in the normal gate: `python -m unittest discover -s tests -t .`. The replay itself is not a gate. A failing build is data.

## The cases

* 10 replay cases on the lab: the 8 checklist cases (`fail`, `long`, `longfail`, `pipe`, `multi`, `gates`, `gates --dry-run`, `nosuch`), `timeout`, and `longfail150` (error at line 150, used by B3a and B3b). B1 uses the first 9.
* B2 matrix: TTY yes/no x `CLAUDECODE` set/unset x override none / `LADDER_AGENT=1` / `LADDER_AGENT=0` = 12 cells. The 6 TTY=yes cells need a pseudo-terminal that this laptop setup does not give. They are `NOT_RUN` (reason `no_pty`) and are listed, never counted as pass.
* B4: 6 fake PR states: green, 1 failed check, pending review, no checks, log not available, API error. Every `gh` call is answered by `fake_gh.py`. No network.
* B6: the frozen Claude sample, 46 slots (see below).

## Scoring rule

* A replay case passes only if every frozen observable matches. A case that cannot run is `NOT_RUN`, listed, never a pass.
* **A false success fails the build at once**, whatever the score. False success: ladder or the agent says success (exit 0, an ok/PASS/green last line, the answer `green: yes`) while the truth is failure or unknown.
* Agent questions: fresh `claude -p` session per question per run, 3 runs, one fixed model id (`claude-sonnet-5-5`), 6 turns, 4 tool calls. A run passes only if every answer in it is right.
* Stored data: labels, booleans, counts and synthetic fixture ids only. Child output text is never stored.

Minimum per build is in `contracts.json` under `builds`. It matches the plan table.

## Frozen Claude sample (B6)

* Source: `research/transcript-audit-2026-11-15.json` in the DevOps repo, last commit 3c57abd, sha256 `40c540fd3307c9d2191d8466330de44db082b1317282f16c4517c70d13505fa9`, generated 2026-11-15T12:37:09Z.
* Definition: Claude calls of `ladder` piped into `tail` 18, `Select-Object` 12, `head` 10, `grep` 4, `sed` 1, `Select-String` 1 = 46, out of 103 Claude ladder calls. Window: all Claude transcripts, first day 2026-08-06, up to the generation time of the source file. Transcripts grew after that; a re-run may count more.
* The 46 comes from `pipe_tax`. `pipe_any` in the same file gives 44 (`Select-Object` 10). Not reconciled: `___`.
* Claude only. Any claim from B6b is limited to Claude calls unless a Codex sample is added.
* Per-slot `need` and `fixture_id` are `___` until ticket 14b (B6a) exports them with a marker test. B0 read no transcript.

## Choices made by B0 (Ahmed may veto before B1)

1. Model id for agent questions: `claude-sonnet-5-5`. The plan names none.
2. The agent "next command" question asks for the command that re-runs all checks after a fix. Frozen answer: `ladder gates`.
3. B2 rule uses the plan text: agent mode = `CLAUDECODE` set and no TTY. Ticket 10 says `CLAUDECODE=1` alone. The plan is later and wins.
4. Override axis has 3 values, not 2 (ticket 10 has two override values).
5. B3 line cap: 45 total lines. The plan says 40 plus the "showing" line. The echo line and the summary line add 2; 2 more lines are spare.
6. `green` = at least 1 check, all pass. No checks is `unknown`, never `yes`. Review state does not change `green`.
7. Timeout: ticket 08's addendum says "timeout", but no ticket defines how a task times out. B1 chooses the knob and fills `timeout_control` only.

## Pre-B1 scores (build = source at commit 517db34; B0 changed no `src/` file)

Full data: `docs/frozen-scores-pre-b1-2026-11-15.json` and `.md`. Re-create with the command above.

| Row | Pass | Fail | Not run | False success |
| --- | --- | --- | --- | --- |
| B1 (9 cases) | 3 (`long`, `gates_dry_run`, `nosuch`) | 6 | 0 | 1 (`pipe` exits 0, must exit 5) |
| B2 (12 cells, plus the B1 rule) | 3 | 12 | 6 (`no_pty`) | 1 |
| B3 (`long`, `longfail150`) | 0 | 2 | 0 | 0 |
| B4 (6 PR states) | 1 (`pr-api-error`) | 5 | 0 | 0 |
| B5 | | | 1 (not built) | 0 |
| Agent questions (5 sets) | | | 5 (no live run) | |

The B2 row counts the 9 B1 cases again, because the B2 pass rule includes the B1 rule. The overall line in the `.md` counts each case once: 4 pass, 19 fail, 12 not run, 1 false success.

The B1 replay found one error in the first draft of the contract: `gates --dry-run` prints the `ladder: using` line, so the draft line count (3) was wrong. The contract now ignores that line for the count. This was fixed before the freeze. `tests/frozen/test_frozen_contract.py` pins the sha256 of `contracts.json`, so any later change fails the gate.

## Not done in B0 (`___`)

* Live agent-question scores for the pre-B1 build. They bill the Console and need Ahmed's yes for the spend.
* TTY=yes matrix cells (no pseudo-terminal).
* Per-slot labels of the Claude sample (B6a).
