# Progress

## 2026-11-20

- Built the core: spec loader, differ, oasdiff adapter, finder (Python and TypeScript), mock server, patch applier, verifier, three proposers, state machine, guard, report writer, benchmark and CLI.
- 36 frozen cases. Local runs before the 2-core timing: answer key 36 of 36 verified, rule baseline 22 of 36 with 0 regressions.
- `./init.sh`: 140 tests pass offline.
- Features passing: F01 to F11, F13, F14, F17.

### Tests proven against a broken case

- `test_planted_git_push_is_blocked`: with `_is_git_push` forced to return False, the test failed ("DID NOT RAISE"). Restored, it passes.
- `test_real_oasdiff_sees_the_removed_field`: failed for real on the first run because oasdiff rejects `--color` with JSON output. Fixed the adapter.
- Verifier regression test: breaks the `name=data["name"]` mapping in a patch, and the verdict is a regression fail.
- Manifest tests: an edited answer key and an extra case file each stop the run.

## Next

1. census.py and a real census run (F16).
2. readme.py, the benches on 2 cores, results files (F12, F15 as "not run", F18).
3. README, CI, docs, study kit, social preview, site (F19, F20).
4. Release check and hand-off (F21, F22).
