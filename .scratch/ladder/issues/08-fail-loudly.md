# 08: fail loudly, summary last, full log on disk

**What to build:** Every task and gates run writes the whole child output to a log file in the temp folder, and ends with 1 summary line on standard output: the result, the step, the exit code and the log path. A passing task gets a closing line too. Checklist item 1 in `docs/talk-checklist-2026-11-15.md`.

**Why:** Today a failed task prints `ladder: step N of M failed (exit X)` to standard error (`src/ladder/tasks.py:28`). In a PowerShell capture with `*>`, that line landed at line 138 of 304, not at the end. Both real `ladder gates` runs in the transcripts were written to a file by hand, then read with `tail` or `grep`.

**Blocked by:** none

**Status:** ready-for-agent

- [ ] Log path: `<tempfile.gettempdir()>/ladder/logs/<task or gates>-<YYYYMMDD-HHMMSS>.log`. Never inside the repo (D18).
- [ ] The log holds every child line after `redact()`, the same text the screen gets. No secret goes into the file (D18).
- [ ] Task end, on standard output, flushed after the last child line:
  `ladder: FAIL test, step 1 of 1, exit 3; full log: <path>` or `ladder: ok test, 2 steps; full log: <path>`
- [ ] Gates keep their `FAIL step ...` and `gates: all N passed` lines and add `full log: <path>` to them.
- [ ] `ladder: using <path>` stays on standard error. Nothing else moves.
- [ ] Skill page and README: "The last line is the result and names the full log. Do not pipe ladder into head or tail."
- [ ] Exit codes do not change.

**Test idea:** Fake runner streams 300 lines and returns 3. Point `tempfile.tempdir` at a `TemporaryDirectory`. Assert the last line of `out` starts with `ladder: FAIL`, and the path in it is a file with all 300 lines. Known negative: a passing task ends with `ladder: ok`. A token in a child line shows as `[redacted]` in the log. A real runner check with a `.qa` child program: run `python -m ladder <task>` with standard output and standard error on 1 pipe, then assert the summary is the last line.

**Size:** about 80 code lines and 120 test lines.
