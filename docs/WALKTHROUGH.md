# Walkthrough

A tour of every file, in the order that makes the code easiest to learn. Read it with the code open.

## 1. Start here

- `README.md`: what driftpatch does, the results and the run guide. Its number blocks are written by `readme.py`.
- `PROJECT_CONTEXT.md`: the one-page summary for an agent or a new reader.
- `CLAUDE.md`: the reading order for an AI agent working in the repo.
- `docs/build/BUILD_PROMPT.md`: the full prompt the build followed.
- `docs/PLAN.md`: the build order and why the baseline comes first.
- `LICENSE`: MIT, copyright Shreyas.

## 2. The sample API

- `examples/acme/specs/acme-orders-v1.json`: the invented Acme Orders API. Every schema has examples, which the mock server serves.
- `examples/acme/specs/acme-orders-v2.json`: the demo change. It renames `total`, removes `note` and adds a required `currency` parameter. Written by `make_cases.py`.
- `examples/acme/clients/python/acme_client/client.py`: a small Python client on `urllib`. `__init__.py` exports it.
- `examples/acme/clients/python/tests/test_client.py`: its tests, which read the base URL from `ACME_BASE_URL`.
- `examples/acme/clients/python/pyproject.toml`: pytest settings for the client.
- `examples/acme/clients/ts/src/client.ts`: the same client in TypeScript, run by Node 22 with type stripping.
- `examples/acme/clients/ts/test/client.test.ts`: its `node:test` tests.
- `examples/acme/clients/ts/package.json`: marks the client as an ES module. No dependencies.

## 3. The pipeline, one stage at a time

- `src/driftpatch/__init__.py`: the version.
- `src/driftpatch/spec.py`: loads a spec, resolves `$ref`, lists operations and picks the request and response schemas. Form bodies count as request bodies, because Stripe sends forms.
- `src/driftpatch/differ.py`: the six kinds. `_Walker` compares schemas, pairs renames and credits each change to every operation that uses it.
- `src/driftpatch/oasdiff.py`: runs the optional oasdiff binary with external refs off and maps its check ids to the six kinds.
- `src/driftpatch/finder.py`: finds call sites. Python uses `ast`. TypeScript uses patterns and a brace scanner. Both limit a change to the functions that call the affected endpoint.
- `src/driftpatch/mock_server.py`: a loopback HTTP server built from a spec. It rejects requests the spec does not allow and answers with examples.
- `src/driftpatch/patch.py`: builds unified diffs from new file text and applies them strictly. Unsafe paths are refused.
- `src/driftpatch/verifier.py`: copies the client to a temp folder, runs its tests against the mock before and after the patch, reads JUnit XML and applies the pass rule.
- `src/driftpatch/proposer_rule.py`: the rule baseline. It fixes renames, removed fields and required parameters with a default, and declines the rest with a reason.
- `src/driftpatch/proposer_oracle.py`: replays a case's answer key. A sanity check, not a proposer.
- `src/driftpatch/proposer_llm.py`: builds the prompt, calls an OpenAI-compatible endpoint in record mode, replays saved answers in replay mode and refuses unsafe answers.
- `src/driftpatch/pipeline.py`: the state machine that ties the stages together. `TRANSITIONS` lists every allowed move.
- `src/driftpatch/guard.py`: the audit hook that blocks any git push and outside connections or lookups. Every command but `census` runs under it.
- `src/driftpatch/report.py`: writes `patch.diff`, `PR.md`, `verification.md` and `verification.json`.
- `src/driftpatch/cli.py`: the `driftpatch` command and its subcommands.

## 4. Measuring it

- `scripts/make_cases.py`: builds the 36 frozen cases, the split and the manifest from spec v1. `--check` rebuilds in memory and compares.
- `bench/cases/`: one folder per case with `case.json`, `new.json` and `expected.diff`.
- `bench/MANIFEST.sha256`: the hash of every frozen file.
- `src/driftpatch/bench.py`: checks the manifest, runs every case, and computes Wilson and bootstrap intervals.
- `scripts/time_bench.py`: times the rule run pinned to two cores and writes `timing.json`.
- `src/driftpatch/census.py`: samples tags of the Stripe and GitHub spec repos, downloads specs into a hashed cache and counts changes by kind.
- `results/bench-rule.json`, `results/bench-oracle.json`, `results/bench-llm.json`: one file per proposer, with every case row and the summary.
- `results/timing.json`: the 2-core timing.
- `results/census.json`: the census counts.
- `fixtures/llm/`: recorded model answers for replay. Empty in this release.

## 5. Writing it up

- `src/driftpatch/readme.py`: writes the README blocks from `results/`. `--check` fails on drift.
- `scripts/make_site.py`: writes `docs/index.html`, the static results page.
- `scripts/make_social_preview.py`: draws `docs/social-preview.png` with the standard library only.
- `scripts/make_demo.sh`: writes `docs/DEMO.md` from a real terminal session.
- `scripts/check_links.py`: checks every relative link and anchor. It never goes online.
- `docs/CENSUS.md`: the census method and tables, written by `census.py`.
- `docs/GITHUB_ABOUT.md` and `docs/topics.txt`: the About box text and topics.
- `docs/PROPOSALS.md`: ideas left for later.

## 6. Tests

- `tests/conftest.py`: the offline guard and shared paths.
- `tests/test_network_guard.py`: proves the offline guard blocks a real outside connect.
- `tests/test_sample_clients.py`: both sample clients pass against a mock of v1.
- `tests/test_differ.py`, `tests/test_oasdiff.py`, `tests/test_finder.py`, `tests/test_mock_server.py`, `tests/test_patch.py`, `tests/test_verifier.py`, `tests/test_rule_proposer.py`, `tests/test_llm.py`: one file per module.
- `tests/test_pipeline.py`: every state transition.
- `tests/test_guard.py`: the no push and no network proof.
- `tests/test_report.py` and `tests/test_cli.py`: the outputs and the command line.
- `tests/test_bench_suite.py`: the manifest, the split and the statistics.
- `tests/test_census.py`: the census with fake tags and downloads.
- `tests/test_readme_sync.py`: the README blocks follow `results/`.
- `tests/test_repo_quality.py`: the quality bar, the study kit and the hand-off files.

## 7. Running and shipping

- `init.sh`: install, lint, test. Run it before and after any change.
- `pyproject.toml`: the package, the `driftpatch` script, pytest and ruff settings.
- `.github/workflows/ci.yml`: CI on Python 3.11, the same steps as `init.sh` plus the `--check` steps.
- `.github/ISSUE_TEMPLATE/`: bug and feature templates.
- `.pre-commit-config.yaml`: the gitleaks hook.
- `.env.example`: the one optional variable, `GROQ_API_KEY`.
- `.gitignore`: keeps the venv, outputs and the census cache out of git.
- `feature_list.json`: every feature with its test command and whether it passes.
- `CHANGELOG.md` and `CONTRIBUTING.md`: release notes and how to change the code.

## 8. Memory and hand-off

- `PROGRESS.md`: what was done, in order, and what is next.
- `DECISIONS.md`: one line per design choice with the reason.
- `BLOCKERS.md`: what could not be done here and what unblocks it.
- `HANDOVER.md`: what a fresh session needs to resume.
- `docs/ENVIRONMENT.md`: the network probes and the build machine.
- `docs/TOOLING.md`: the tools used and how they were installed.
- `docs/DEMO.md`: a real transcript.
- `docs/WALKTHROUGH.md`: this file.
- `docs/INTERVIEW_QA.md`: questions and answers for an interview.
- `docs/RELEASE_CHECK.md`: the release checks and their results.
- `docs/HUMAN_STEPS.md`: what only Shreyas can do, in order.
- `docs/handoff/COWORK_PROMPT.md`: a prompt for the browser steps.
