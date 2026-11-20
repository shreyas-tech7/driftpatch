# Interview questions and answers

Questions someone might ask about driftpatch, with short answers that point at the code and the results files. Numbers live in `results/` and the README, so check them there before you quote one.

## What problem does driftpatch solve?

A hand-written API client breaks when the API ships a spec change. Diff tools list what changed in the spec, but someone still has to find the broken lines and fix them. driftpatch does that and then proves the fix: `src/driftpatch/differ.py` lists the changes, `src/driftpatch/finder.py` finds the call sites, a proposer writes the patch and `src/driftpatch/verifier.py` runs the client's tests before and after.

## Why does a verifier gate every patch?

A patch that looks right can still be wrong. It can fix the renamed field and break the parser next to it. So no patch is called a fix until it has run. The verifier gates every patch with one rule in `verify` in `src/driftpatch/verifier.py`: the patch applies, it touches no test file, every test that failed before now passes, no test that passed before now fails, and the same non-empty set of tests ran both times. The proposer can be rules, a model or a person, and the gate is the same. That is also what makes an LLM proposer safe to try: a bad answer fails the gate and is reported, not shipped.

## Why must the patch not touch test files?

A proposer that can edit tests can make any patch pass by deleting the failing test. `is_test_file` in `src/driftpatch/verifier.py` rejects such a patch, and `parse_answer` in `src/driftpatch/proposer_llm.py` refuses a model answer that names a test file.

## How are breaking changes classified?

Into six kinds: removed endpoint, renamed field, removed field, new required parameter, changed type and changed enum. `_Walker` in `src/driftpatch/differ.py` walks every operation's parameters, request body and first 2xx response, resolves `$ref`s, and compares old and new schemas field by field. Side matters. A new required field breaks a request, not a response. A removed enum value breaks a request, and a new enum value can break a strict response parser. Each change is classified once per schema and credited to every operation that uses that schema, so one shared model does not count as a hundred changes.

## How does it tell a rename from a removal?

The spec does not say. A removed field and an added field of the same type in the same schema are paired when their names are similar enough (difflib ratio at least 0.3) or when they are the only such pair. `x-renamed-from` in the new spec overrides the guess. It is a heuristic and the README says so. oasdiff has no rename check at all, it reports a removal and an addition.

## Why build the baseline before the LLM?

The rule baseline in `src/driftpatch/proposer_rule.py` sets the bar. Building the baseline before the LLM means every LLM number has something to be compared with, and a model that cannot beat a page of rules is not worth its tokens. The baseline is free, deterministic and fast, so it also runs in CI. The answer key proposer in `src/driftpatch/proposer_oracle.py` goes further down: it replays the known fix and proves every case can be solved and that the verifier accepts a correct patch.

## What does the rule baseline decline, and why?

It fixes renames, removed fields and new required parameters that have a default in the spec. It declines removed endpoints, type changes, enum changes and required parameters with no default, each with a reason in the report. Those need judgment about intent, such as which value to send or what replaces a removed endpoint. Guessing would produce patches that pass by luck.

## What do the synthetic numbers not prove?

The suite in `bench/cases/` is built by `scripts/make_cases.py` from one invented API and two small clients. The synthetic numbers do not prove that driftpatch fixes real clients at that rate. Real clients are bigger, use other HTTP libraries, and have tests that miss things. The numbers do prove narrower facts: the pipeline runs end to end, the verifier accepts the known fixes and rejects regressions, and the rule baseline handles the kinds it claims. The census in `docs/CENSUS.md` is the real-world part, and it measures how often changes happen, not how well they are fixed.

## How do you keep the benchmark honest?

The cases are frozen. `bench/MANIFEST.sha256` holds a hash of every case file, the v1 spec and both clients, and `check_manifest` in `src/driftpatch/bench.py` stops the run on any change or extra file. The dev and held-out split is a seeded shuffle written at case build time. The README reads every number from `results/` through `src/driftpatch/readme.py`, and `driftpatch readme --check` fails in CI when they drift.

## Why Wilson intervals and a bootstrap?

With a few dozen cases a pass rate alone overstates what we know. `wilson` in `src/driftpatch/bench.py` gives a 95% interval for the share of cases verified that stays sensible near zero and one. The test pass rate after the patch is a mean over cases, so it gets a seeded bootstrap interval from `bootstrap_mean`. Regressions and patch size are plain counts.

## How do you know the tool never pushes or calls out?

`src/driftpatch/guard.py` installs a Python audit hook. It sees every `subprocess.Popen` and every `socket.connect`, blocks `git push` in any form, and blocks any connection that is not loopback or the configured model host. `driftpatch run` turns it on by itself. `tests/test_guard.py` runs the whole pipeline under it, then plants a `git push` and a remote connect and checks both are blocked. That test was seen to fail when the push check was broken on purpose.

## How does the mock server work?

`src/driftpatch/mock_server.py` builds a tiny HTTP server on 127.0.0.1 from the new spec. It checks each request against the spec (path, method, required parameters, body fields, no unknown fields) and answers with the spec's examples. A client still sending the old field name gets a 400, which is what makes its tests fail before the patch.

## Why does the Python finder use ast and the TypeScript one patterns?

Python ships a parser in the standard library, so `_py_sites` in `src/driftpatch/finder.py` uses real syntax trees. A TypeScript parser would mean an npm dependency, which the build rules ruled out. So `_ts_sites` uses patterns and a brace scanner. It works on the sample client and is marked experimental in the README.

## Why do proposers return whole files instead of diffs?

Models write broken diffs often: wrong line counts, missing context. Asking for the whole new file is easier to check. driftpatch builds the unified diff itself in `src/driftpatch/patch.py`, and the verifier applies it with a strict applier that rejects unsafe paths.

## How does the LLM proposer stay reproducible?

In record mode it calls an OpenAI-compatible endpoint and saves each answer under `fixtures/llm/`, named by a hash of the prompt and model. Replay mode reads only those files, so the run is offline and repeatable. On the build machine the model hosts were blocked and no key was set, so there are no recordings and the LLM row says "not run" (`BLOCKERS.md`).

## What did the census find?

`src/driftpatch/census.py` sampled tagged releases of the Stripe and GitHub REST specs without cloning, diffed consecutive pairs and counted the kinds. The counts are in `results/census.json` and `docs/CENSUS.md`. The main lesson is that counting depends on the method: oasdiff counts each place a change shows up and gives far larger numbers than the built-in differ, which counts each change once.

## What would you build next?

A real TypeScript parser behind an optional install, recorded LLM runs on a free provider, and a few real open-source clients as extra cases. Each is listed in `docs/PROPOSALS.md`.
