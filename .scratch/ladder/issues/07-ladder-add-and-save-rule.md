# 07: ladder add and the save scripts rule

**What to build:** `ladder add` writes a new task into the repo's `ladder.toml` safely, and the skill tells every agent to save reusable scripts in `scripts/ladder/` and add them as tasks (decisions D19 to D22).

**Blocked by:** 02, 04

**Status:** ready-for-agent

- [ ] `ladder add <name> --about TEXT --run LINE [--run LINE ...] [--shell bash] [--confirm]`
- [ ] Refuses outside a git repo, an existing task name, and a core job name
- [ ] Creates `ladder.toml` at the repo root when missing
- [ ] Never breaks the file: the new text is parsed by ladder's own parser before it is written; text already in the file is kept byte for byte
- [ ] Skill page and the AGENTS.md section carry the D21 rule
- [ ] `init` output mentions `scripts/ladder/`
