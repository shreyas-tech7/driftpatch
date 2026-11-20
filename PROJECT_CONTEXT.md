# Project context

## What it is

driftpatch reads two versions of an OpenAPI spec, lists the breaking changes, finds the client code each change breaks, proposes a patch and checks the patch by running the client's own tests against a mock server built from the new spec. It writes a diff, PR text and a verification report. It never pushes and never opens a pull request.

## Who it is for

Teams that keep a hand-written client for an API they do not own, and reviewers who want proof before they merge a fix.

## Pieces

- `src/driftpatch/spec.py`: load and resolve specs.
- `differ.py`: built-in differ with six kinds. `oasdiff.py`: optional adapter.
- `finder.py`: Python (ast) and TypeScript (patterns) call-site finder.
- `mock_server.py`: loopback mock of a spec that validates requests.
- `patch.py`: diff writer and strict applier. `verifier.py`: before and after test runs.
- `proposer_rule.py`, `proposer_oracle.py`, `proposer_llm.py`: the three proposers.
- `pipeline.py`: the state machine. `guard.py`: no push and no network guard.
- `report.py`: the three outputs. `bench.py`: the frozen benchmark. `census.py`: the real spec census.
- `readme.py`: writes README tables from `results/`.

## Data

- `examples/acme/`: an invented Acme Orders API, v1 spec, a Python client and a TypeScript client.
- `bench/cases/`: 36 frozen cases made by `scripts/make_cases.py`, checked by `bench/MANIFEST.sha256`.
- `results/`: benchmark and census JSON. The README reads numbers only from here.

## Rules

- Tests run offline. A conftest guard fails any non-loopback connection.
- Every subprocess has a timeout.
- No numbers typed into the README. Run `driftpatch readme`.
- No force push, no tags, no posts outside this repo.

## Commands

- `./init.sh`: install, lint, test.
- `driftpatch run OLD NEW CLIENT`: the whole pipeline.
- `driftpatch bench --proposer rule`: the benchmark.
- `driftpatch census`: the census (needs the network).
- `driftpatch readme`: rewrite the README tables.

## Status

See PROGRESS.md and feature_list.json.
