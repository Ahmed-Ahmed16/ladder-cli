# Ticket 01 plan

Use Python 3.12, setuptools, a src package, and no runtime dependencies.
Follow docs/decisions.md, docs/spec.md, and ticket 01 in .scratch/ladder/issues/.
Build in this repo. Do not commit, push, or install outside it.

1. Write a failing help test. Add packaging, the CLI entry, and both launch paths.
2. Write failing error tests. Add plain errors and optional debug traces.
3. Write failing doctor tests. Add version and auth checks through the runner.
4. Write failing comments tests using the Rust JSON. Port query, parse, and render.
5. Write failing summary tests. Add markup removal and nested details handling.
6. Check the real runner with local child programs. Check packaging inside the repo.
7. Write README and ignore rules. Review code, tests, and docs. Run both test commands.

Files: pyproject.toml, .gitignore, README.md, src/ladder/{__init__,__main__,cli,process,pr}.py,
tests/{__init__,test_cli}.py. The runner owns command printing. FakeRunner does the same.
The CLI owns error printing and returns the exit code.

Boundary cases: empty arguments, bad PR numbers, bad JSON, null PR, absent fields,
empty threads, null and numbered lines, resolved threads, nested and unclosed markup,
missing programs, failed programs, secrets in commands and errors, old Python.

Ticket 01 omits config checks. Only 4 of the 7 Rust tests concern comments.
The other 3 concern waiting for reviews. No outside install or live auth check is allowed.

Verification: each implementation step had a failing check before code was added.
The extra summary edge cases passed without another code change.
The real runner passed local child program checks. Editable install passed in .venv.
Setuptools came from an existing local tool runtime after network access was refused.
Independent review found broad masking and quoted secret gaps. Regression checks failed first,
then passed after fixes. Docs ignore exceptions and secret flags also passed local checks.
