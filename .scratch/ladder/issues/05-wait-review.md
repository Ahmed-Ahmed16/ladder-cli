# 05: pr wait-review

**What to build:** `ladder pr wait-review <n>` waits until each login in `[review] wait_for` has reviewed the PR's newest commit. `--bot <login>` overrides the list. An empty or missing list stops at once with a clear message. A timeout stops with a clear error (D16).

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] Review state read from PR reviews by login and commit id, through gh
- [ ] Poll every 30 s; timeout default `___` (check werdy's default first)
- [ ] Tests for not started, done for some logins, done for all, timeout, empty list
