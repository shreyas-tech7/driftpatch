# Proposals

Ideas that are out of scope for v0.1.0-rc1. Each one needs a test plan before it is built.

## A real TypeScript parser as an option

The TypeScript finder uses patterns and a brace scanner. An optional install of the TypeScript compiler API would give real syntax trees, like the Python finder. The pattern finder stays the default, because it needs no npm packages.

## Recorded LLM runs

Record mode is built and tested with a fake transport. A run on a free provider over the whole suite would fill the LLM row with real numbers. It needs network access to the provider and a key, which the build machine did not have.

## Real clients as extra cases

A few small open-source clients for public APIs, with their own tests, frozen at one commit, would test the finder and the rules on code nobody wrote for this repo. Each needs a license check and a mock that serves what their tests expect.

## Composed schemas in the differ

The built-in differ skips `allOf`, `oneOf` and `anyOf`. Stripe uses `anyOf` a lot. Merging `allOf` and comparing each branch of `oneOf` and `anyOf` would make the census counts less of a floor.

## A base URL setting per client

The verifier passes the mock URL as `ACME_BASE_URL`. A `--base-url-env` flag would let any client read its own variable name.
