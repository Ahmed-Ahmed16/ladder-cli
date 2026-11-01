# Glossary

**Core job**: a job ladder knows by itself, the same in every repo. Example: `pr comments`, `doctor`.

**Task**: a job 1 project defines in its `ladder.toml`: a name, 1 line about it, and the command it runs.

**Gates**: the checks run before a commit, the same ones CI runs.

**Front door**: the single place an agent looks to find any job, which is `ladder list`.

**Reviewer**: a GitHub login whose review a PR waits for. It can be a bot or a person.

**Throwaway script**: a script an agent writes for a job that already exists, used once, then lost. Ladder exists to stop these.
