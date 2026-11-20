# Handover

For a fresh session that picks this up.

- Repo: /home/user/driftpatch, branch `claude/build-driftpatch`. Remotes: origin (GitHub, private) and backup (/mnt/project-files/portfolio/remotes/driftpatch.git).
- Push with `git push -u origin HEAD` and `git push backup HEAD`. Never push main, never tag, never force push.
- Run `./init.sh` before and after a change. It puts `$(go env GOPATH)/bin` on PATH for oasdiff.
- Read PROGRESS.md for what is done and next, BLOCKERS.md for what cannot be done here, DECISIONS.md for why.
- The LLM row stays "not run" unless a key and network access appear. Do not invent fixtures.
- At the end: bundle to /mnt/project-files/portfolio/bundles/driftpatch.bundle, report to /mnt/project-files/portfolio/reports/driftpatch.md, and set row 7 of /mnt/project-files/portfolio/QUEUE.md.

Release commit: 5d362b856e0005b60e3d8e8e19831e921ebe42b7.
