# 04: install-skill and init

**What to build:** `ladder install-skill` writes the skill page (shipped in the package) to `~/.claude/skills/ladder/` and `~/.agents/skills/ladder/`, and a marked section in `~/.codex/AGENTS.md` (D17). `ladder init` writes a starter `ladder.toml` and prints the 2 lines for the repo's `AGENTS.md`.

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] A rerun replaces the marked section, never doubles it; text outside the markers is untouched
- [ ] `init` refuses to overwrite an existing `ladder.toml`
- [ ] Tests use a temporary home folder, never the real one
- [ ] After install, a fresh Codex session is checked for whether it finds the skill; result recorded in `docs/decisions.md`
