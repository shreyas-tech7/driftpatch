# Changelog

## v0.1.0-rc1 (2026-11-20)

Release commit: this commit.

First release candidate.

- Built-in OpenAPI differ with six kinds of breaking change, and an optional oasdiff adapter.
- Call-site finder for Python (ast) and TypeScript (patterns, experimental).
- Mock server built from a spec, and a verifier that runs the client tests before and after a patch.
- Three proposers: rule baseline, answer key (sanity check) and an LLM proposer with record and replay modes.
- State machine pipeline with a guard that blocks `git push` and outside connections.
- Frozen benchmark of 36 cases with a SHA-256 manifest, Wilson and bootstrap intervals.
- Census of breaking changes across sampled Stripe and GitHub spec releases.
- README tables, results page and social preview written from `results/`.

Not in this release: LLM numbers (no model endpoint was reachable from the build machine).
