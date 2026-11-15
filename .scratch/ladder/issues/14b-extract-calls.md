# 14b: extract real ladder calls from transcripts

**What to build:** A saved script that reads local Claude Code transcripts and writes every real ladder call, plus what the agent piped it into, as a calls file for ticket 14. Its output stays outside this repo. Checklist item 8 in `docs/talk-checklist-2026-11-15.md`.

**Why:** A hand count on 2026-11-15 found about 23 distinct ladder calls; about 30% were piped into `head`, `tail` or `grep`. 6 calls could not be read by eye because of escaped quotes. A script that parses the JSON gets exact numbers, and the pipe tax becomes a number to watch after each ticket.

**Blocked by:** 14 (calls file format)

**Status:** ready-for-agent

- [ ] `scripts/ladder/extract_calls.py <transcripts folder> <out.jsonl>` reads each `*.jsonl` line as JSON and keeps Bash and PowerShell tool calls whose command runs `ladder`. A path that only holds the word `ladder` does not count.
- [ ] Split the command at `;`, `&&` and `|`. Write the ladder part as `argv` and the part after a `|` as `next`.
- [ ] Count a copied session once: drop calls with the same command text and the same timestamp.
- [ ] End with 1 summary line: `extract: 23 calls, 7 piped (30%), out: <path>`.
- [ ] The script refuses an output path inside this repo, because transcripts hold company names (D3).
- [ ] Skip folders named `worktrees`.

**Test idea:** A made up transcript in a temp folder with 4 tool calls: `ladder list`, `ladder gates 2>&1 | tail -15`, `cd x/ladder && git status` (not a call), and 1 copy of the 1st call. Expect 2 calls, 1 piped with `next` = `tail -15`. Known negative: an output path inside the repo exits 1 with a plain error.

**Size:** about 90 code lines and 80 test lines.
