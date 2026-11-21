# Contributing

## Setup

```bash
./init.sh
```

It makes `.venv`, installs driftpatch with its dev tools, runs ruff and runs every test offline. Run it before and after a change.

## Rules

- One change per commit, with a test that fails before the change and passes after it.
- Tests run offline. The conftest guard fails any connection that is not to 127.0.0.1.
- Every subprocess call needs a timeout.
- Never type a number into the README. Change the results files with a real run, then run `driftpatch readme`.
- The frozen cases in `bench/cases/` are made by `scripts/make_cases.py`. Do not edit them by hand. If you change the script, run it and commit the new manifest in the same commit, and say why in DECISIONS.md.

## Adding a change kind

1. Add the kind to `src/driftpatch/differ.py` with a test in `tests/test_differ.py`.
2. Teach the finder where the kind shows up in client code.
3. Either teach the rule proposer to fix it or make it decline with a reason.
4. Add cases for it to `scripts/make_cases.py`.

## Adding a client language

Add a finder in `src/driftpatch/finder.py`, a test runner in `src/driftpatch/verifier.py` that writes JUnit XML, and a sample client under `examples/acme/clients/`.
