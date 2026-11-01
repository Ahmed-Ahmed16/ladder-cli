# 03: ladder gates

**What to build:** `ladder gates` runs the `[gates]` steps from `ladder.toml`, prints pass or fail per step, stops at the first failure. `--dry-run` only prints them. With `ci` set, a step missing from that CI file gives a warning, never a failure (D15).

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] Pass and fail line per step, exit code matches
- [ ] `--dry-run` runs nothing
- [ ] Drift warning with a known positive and a known negative test
- [ ] No `[gates]` block gives a plain message
