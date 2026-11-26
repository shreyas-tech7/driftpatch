# Handover

For a fresh session that picks this up.

- Repo: the local clone, branch `claude/build-driftpatch`. Remote: origin (GitHub).
- Push with `git push -u origin HEAD`. Never push main, never tag, never force push.
- Run `./init.sh` before and after a change. It puts `$(go env GOPATH)/bin` on PATH for oasdiff.
- Read PROGRESS.md for what is done and next, BLOCKERS.md for what cannot be done here, DECISIONS.md for why.
- The LLM row stays "not run" unless a key and network access appear. Do not invent fixtures.

Release commit: 5d362b856e0005b60e3d8e8e19831e921ebe42b7.
