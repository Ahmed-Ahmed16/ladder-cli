# 14: replay runner on a lab fixture

**What to build:** A saved script that runs a list of ladder calls against 2 ladder builds (old and new) inside a copy of a lab fixture, and prints what changed: exit code, line count and last line. Checklist item 8 in `docs/talk-checklist-2026-11-15.md`.

**Why:** The talk: the commands agents really ran are the test cases, and what the agent did next is a rough answer key. Replay them on the old and the new build. Today ladder has fake runner tests only.

**Blocked by:** none (more useful after 08 and 11, which change the output it compares)

**Status:** ready-for-agent

- [ ] Fixture `tests/fixtures/lab/`: `gen.py` and the `ladder.toml` from the lab section of `docs/talk-checklist-2026-11-15.md`. Made up content only (D3).
- [ ] Calls file, JSON lines, 1 call each: `{"argv": ["longfail"], "next": "tail -15"}`. `next` is optional and only shown in the report.
- [ ] `scripts/ladder/replay.py <calls.jsonl> --old <ladder exe> --new <ladder exe>`: for each call, copy the fixture into a temp folder, run `git init`, run both builds with standard output and standard error on 1 pipe, and record exit code, line count and last line.
- [ ] Report: 1 row per call with old and new values; changed cells marked `*`; 1 summary line at the end (`replay: 8 calls, 3 changed`).
- [ ] Add it as a task with `ladder add replay ...` (D20). Needs the repo's `ladder.toml` (ticket 13, optional item) or creates it.
- [ ] A committed sample `tests/fixtures/lab/calls.jsonl` with the 8 lab calls.
- [ ] The script never reads a transcript. Ticket 14b makes real calls files, kept outside the repo.

**Test idea:** Run the script with the same build as old and new on the sample calls: 0 changed, exit 0. Known negative: point `--new` at a small stub program that prints 1 extra line; the report marks the line count changed for every call.

**Size:** about 110 code lines, 30 fixture lines and 60 test lines.
