# ladder

Ladder runs common project jobs from 1 command.
It reads PR review threads and checks the tools it needs.

Requires Python 3.12 or newer. It has no runtime packages to install.
The commands need `git` and `gh` on PATH, with `gh` signed in.

Install from GitHub:

```console
pip install git+https://github.com/Ahmed-Ahmed16/ladder-cli
```

For local work, run this from the repo root:

```console
pip install -e .
```

Commands:

```console
ladder help
ladder doctor
ladder pr comments 82
```

Add `--all` to include resolved threads. Add `--full` for whole comment bodies.
The default shows the first 3 plain lines of each comment.
`python -m ladder` accepts the same arguments.
If doctor reports `FAIL`, fix that check and run it again. A failed check exits 1.

Run tests from the repo root. No install or GitHub access is needed:

```console
python -m unittest discover -s tests -t .
```

Plain `python -m unittest discover` also works.
