# 01: Tracer bullet: install, help, doctor, pr comments

**What to build:** On a Windows laptop with Python 3.12, `pip install` of this repo puts a `ladder` command on PATH. `ladder help` lists the core jobs. `ladder doctor` reports whether `git`, `gh` and a signed in `gh` are ready, plus the Python version, 1 line each, and exits 0 only when all pass. `ladder pr comments <n> [--all] [--full]` shows a PR's review threads exactly as werdy's `pr.rs` does (spec, Implementation Decisions). Every outside command goes through the runner seam and is printed before it runs.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] Python 3.12 package, standard library only, console entry point `ladder`, installable with `pip install` from the repo folder and from `git+https://...`
- [ ] Runner seam: 1 object that runs and captures outside commands and prints each one first; the CLI entry takes argv, a runner and an output stream and returns an exit code
- [ ] `help` and `--help` work; an unknown job gives 1 plain error line and exit code 1
- [ ] `doctor`: git, gh, gh auth status (exit code only, its output never printed), Python version; 1 line per check; overall pass or fail line; exit code matches
- [ ] `pr comments`: werdy's 7 `pr.rs` tests that cover comments ported with the same saved JSON (thread parse, wrong PR number error, render hides resolved unless `--all`, unresolved first, summary drops markup and `<details>`), plus a test that `--full` keeps the whole body
- [ ] Every failure is 1 plain line on stderr, exit code 1, no Python trace
- [ ] Each check has a known positive and a known negative test
- [ ] `python -m unittest discover` passes with 0 failures
- [ ] README with install and the 3 commands
- [ ] Installed for Ahmed and `ladder doctor` confirmed from his own shell, outside the sandbox
