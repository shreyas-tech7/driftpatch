# Decisions

One line per choice: the options weighed and the reason.

- 2026-11-20 Name: picked `driftpatch` (options: driftpatch, patchdrift, specdrift). PyPI `https://pypi.org/pypi/driftpatch/json` and npm `https://registry.npmjs.org/driftpatch` both answered 404 on 2026-11-20. The brief records a clean web check on 2026-11-19. It matches the repo name, so no rename step.
- 2026-11-20 Branch: built on `claude/build-driftpatch` from a fresh first commit, because origin had no commits and the coordinator brief says never to create main.
- 2026-11-20 Spec format: JSON first, YAML only when PyYAML is installed (options: add PyYAML, JSON only). The brief allows no new dependency, and both census specs are JSON.
- 2026-11-20 Kinds: six kinds, the five in the brief plus `removed-field` (options: fold removals into renamed-field, add a sixth kind). A removed property with no same-type partner is not a rename, and the rule proposer needs to know the difference.
- 2026-11-20 Rename detection: pair a removed and an added property of the same type when the name similarity ratio is at least 0.3 or when they are the only same-type pair. `x-renamed-from` wins when present. oasdiff has no rename check, so this is a heuristic.
- 2026-11-20 Patch driver: the built-in differ drives the patch even when oasdiff is installed (options: map oasdiff findings into patches). oasdiff findings lack the structured old and new names that a patch needs. oasdiff findings go into the report instead.
- 2026-11-20 oasdiff flags: always pass `--allow-external-refs=false`, because the help text says external refs allow SSRF on untrusted specs.
- 2026-11-20 Finder scope: look for a changed field only inside functions that call an affected endpoint, the helpers they call (two hops) and their direct callers (options: whole file). A whole-file rename would touch `Order.status` when only `Refund.status` changed (case C007).
- 2026-11-20 Test runner output: read JUnit XML from pytest (`--junitxml`) and from Node (`--test-reporter=junit`) to get per-test results (options: parse console output). JUnit XML is stable across versions.
- 2026-11-20 TypeScript: run the TS client with Node 22 type stripping and `node --test`, no npm packages (options: tsc, ts-node). The brief says no new npm dependency.
- 2026-11-20 Pass rule: a patch passes only if it applies, touches no test file, every failing test now passes, no passing test fails, and the same non-empty test set ran. A case where nothing failed before is a fail with the reason "nothing to fix".
- 2026-11-20 Patch format: proposers return new file text, driftpatch builds a unified diff, and the verifier applies that diff with a strict applier (options: let proposers emit diffs). Models write broken diffs often. Full files are easier to check.
- 2026-11-20 LLM answers: full new file text inside `<file path="...">` blocks. Paths outside the files sent, test files and unsafe paths are rejected.
- 2026-11-20 Oracle proposer: added a proposer that replays each case's answer key. It is not a real proposer. It proves each case is solvable and that the verifier accepts a correct patch. It shows in the README as a sanity row.
- 2026-11-20 Suite: 36 cases (21 Python, 15 TypeScript), one or two changes each, built by `scripts/make_cases.py` from spec v1. 25 dev and 11 held out, split by a seeded shuffle (seed 20261120).
- 2026-11-20 Frozen manifest covers the case files and the spec and clients they depend on, so an edit to the sample client also shows.
- 2026-11-20 Metrics: cases verified with a Wilson 95% interval, test pass rate after the patch with a bootstrap 95% interval (seed 7, 2,000 rounds), regressions and patch size as plain counts (no interval, they are fixed counts on a fixed suite).
- 2026-11-20 When a proposer offers no patch, its test pass rate for that case is the unpatched pass rate on the new spec, because that is what the user is left with.
- 2026-11-20 Guard: `driftpatch run` itself runs inside the audit-hook guard by default, not only in the test. The test checks both the tool run and a planted bad call.
- 2026-11-20 Skills: the permission system denied `npx skills add` for ponytail, humanizer, security-audit and caveman. Per the prompt I did not try another install route. I used the skills already present (superpowers, the built-in security-audit and simplify skills) and applied the Ponytail and humanizer rules by hand.
- 2026-11-20 Order of work: the core modules were written in one pass before their tests, then each test was added and proven against a planted broken case (listed in PROGRESS.md). This departs from strict test-first order. The evidence rule (seen to fail, then pass) still holds for every guard test.
