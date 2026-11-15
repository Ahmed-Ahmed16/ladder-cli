# 11: cap task and gate output in agent mode

**What to build:** In agent mode, a task or gate step shows the first 10 and the last 30 lines of its output, with 1 marker line between them that says how many lines were cut and where the full log is. Human mode keeps the full stream. Checklist items 3 and 4 in `docs/talk-checklist-2026-11-15.md`.

**Why:** Task output streams every line today (`src/ladder/process.py:132`). In the transcripts, 5 of about 23 ladder calls were cut with `head` or `tail`. The first lines matter too: in the lab the real error was line 1 of 302, so `tail` alone hides it.

**Blocked by:** 08 (log path), 10 (mode)

**Status:** ready-for-agent

- [ ] `Runner.stream` takes a cap. In agent mode it prints lines 1 to 10 live, keeps the last 30 in a `collections.deque`, and at the end prints the marker, then those 30.
- [ ] Marker: `... 260 lines cut; full log: <path> ...`.
- [ ] No marker when the output has 40 lines or fewer; every line prints.
- [ ] The log file from ticket 08 still gets every line.
- [ ] The summary line from ticket 08 stays the last line.
- [ ] 10 and 30 are named constants. `___` tune them after the replay in ticket 14b.
- [ ] Skill page: "In agent mode long output is cut; the marker names the full log. Set `LADDER_AGENT=0` for all lines."

**Test idea:** Fake runner with 300 lines in agent mode: `out` holds 10 lines, the marker with `260 lines cut`, 30 lines, then the summary; the log holds all 300. Known negative: 35 lines give no marker. Human mode with 300 lines prints all 300. Lab check: `ladder longfail` from `docs/talk-checklist-2026-11-15.md` shows the `ERROR-database-not-found` line.

**Size:** about 70 code lines and 100 test lines.
