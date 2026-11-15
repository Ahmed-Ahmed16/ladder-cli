# 12: pr comments says what it left out

**What to build:** `ladder pr comments` says when it hid or cut something, and which flag gets it. Checklist item 3 in `docs/talk-checklist-2026-11-15.md`.

**Why:** The query reads `reviewThreads(first: 100)` and `comments(first: 50)` (`src/ladder/pr.py:10`, `:16`) and never says when more exist. Resolved threads are hidden and bodies are cut to 3 lines, with no hint about `--all` or `--full`. The talk: big output should print less by default and say how to get more.

**Blocked by:** none

**Status:** ready-for-agent

- [ ] The query also asks `reviewThreads { totalCount pageInfo { hasNextPage } }` and `comments { totalCount }`.
- [ ] When threads were not all read: `note: read the first 100 of 140 threads`.
- [ ] When a thread has more than 50 comments: `note: <path>:<line> shows 50 of 63 comments`.
- [ ] When resolved threads were hidden: `2 resolved threads hidden; add --all`.
- [ ] When at least 1 body was cut: `bodies cut to 3 lines; add --full`.
- [ ] Each note prints only when its case happens, at the end, after the threads.
- [ ] Full pagination with `$endCursor` is out of scope. Open a new ticket if a real PR passes 100 threads.
- [ ] The existing saved JSON tests still pass; old answers with no `pageInfo` give no note.

**Test idea:** Saved JSON with `hasNextPage: true` and `totalCount: 140` prints the 100 of 140 note; known negative: `hasNextPage: false` prints none. A 5 line body prints the `--full` hint; bodies of 3 lines or fewer print none. `--all` prints no hidden count.

**Size:** about 40 code lines and 80 test lines.
