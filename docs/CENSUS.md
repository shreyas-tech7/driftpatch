# Census of breaking changes in real OpenAPI histories

This file is written by `driftpatch census` from `results/census.json`. Do not edit the numbers by hand.

Run on 2026-11-20. Samples per repo: 20.

## Method

1. List each repo's tags with `git ls-remote --tags`. Nothing is cloned.
2. Sort the tags by version and take evenly spaced ones, always the first and the last.
3. Download the spec at each sampled tag from raw.githubusercontent.com into a local cache named by the SHA-256 of the URL.
4. Diff each consecutive pair with the built-in differ. When oasdiff is installed, diff the pair with `oasdiff breaking` too.

The built-in differ counts one change per field per schema, and credits every operation that uses the schema to that one change.
oasdiff counts one finding per place it shows up, so one changed shared schema can give thousands of findings.
The built-in differ skips `allOf`, `oneOf` and `anyOf` schemas. Stripe uses `anyOf` a lot, so the built-in counts are a floor.

## Built-in differ, changes by kind

| Repo | Tags listed | Pairs | Pairs with a breaking change | removed-endpoint | renamed-field | removed-field | new-required-parameter | changed-type | changed-enum | Total |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| stripe/openapi | 2602 | 19 | 19 | 69 | 37 | 170 | 3 | 2 | 203 | 484 |
| github/rest-api-description | 18 | 17 | 7 | 67 | 7 | 74 | 24 | 19 | 14 | 205 |

## oasdiff findings, mapped to the same kinds

| Repo | Kind | Findings |
| --- | --- | --- |
| stripe/openapi | changed-enum | 492413 |
| stripe/openapi | other | 70503 |
| stripe/openapi | removed-field | 22007 |
| stripe/openapi | changed-type | 12240 |
| stripe/openapi | removed-endpoint | 58 |
| stripe/openapi | new-required-parameter | 10 |
| stripe/openapi | all | 597231 |
| github/rest-api-description | other | 994 |
| github/rest-api-description | changed-type | 136 |
| github/rest-api-description | changed-enum | 87 |
| github/rest-api-description | removed-endpoint | 50 |
| github/rest-api-description | removed-field | 39 |
| github/rest-api-description | new-required-parameter | 22 |
| github/rest-api-description | all | 1328 |

## Pairs

### stripe/openapi

| From | To | Built-in | oasdiff |
| --- | --- | --- | --- |
| v1 | v138 | 61 | 52929 |
| v138 | v275 | 80 | 76107 |
| v275 | v412 | 10 | 41949 |
| v412 | v549 | 25 | 18565 |
| v549 | v685 | 8 | 35268 |
| v685 | v822 | 21 | 20251 |
| v822 | v959 | 19 | 14403 |
| v959 | v1096 | 18 | 18354 |
| v1096 | v1233 | 6 | 13101 |
| v1233 | v1370 | 25 | 38833 |
| v1370 | v1507 | 6 | 39416 |
| v1507 | v1644 | 102 | 28068 |
| v1644 | v1781 | 7 | 22464 |
| v1781 | v1918 | 8 | 20012 |
| v1918 | v2054 | 16 | 12199 |
| v2054 | v2191 | 14 | 43706 |
| v2191 | v2328 | 23 | 57276 |
| v2328 | v2465 | 11 | 21461 |
| v2465 | v2602 | 24 | 22869 |

### github/rest-api-description

| From | To | Built-in | oasdiff |
| --- | --- | --- | --- |
| v0.0.1 | v0.0.2 | 0 | 0 |
| v0.0.2 | v0.0.3 | 0 | 0 |
| v0.0.3 | v0.0.4 | 1 | 1 |
| v0.0.4 | v0.0.5 | 5 | 5 |
| v0.0.5 | v0.0.6 | 1 | 22 |
| v0.0.6 | v1.0.0-rc.1 | 16 | 11 |
| v1.0.0-rc.1 | v1.0.0-rc.2 | 0 | 0 |
| v1.0.0-rc.2 | v1.0.0-rc.3 | 0 | 0 |
| v1.0.0-rc.3 | v1.0.0-rc.4 | 0 | 0 |
| v1.0.0-rc.4 | v1.0.0 | 0 | 0 |
| v1.0.0 | v1.1.0 | 0 | 0 |
| v1.1.0 | v1.1.1 | 0 | 0 |
| v1.1.1 | v1.1.2 | 0 | 0 |
| v1.1.2 | v1.1.3 | 0 | 0 |
| v1.1.3 | v1.1.4 | 77 | 1171 |
| v1.1.4 | v2.0.0 | 94 | 103 |
| v2.0.0 | v2.1.0 | 11 | 15 |

## What this does not show

- A sampled pair spans many releases, so a change that was added and then removed between two samples is not seen.
- Both counts treat a new response enum value as breaking, because a strict client may reject it. Many clients ignore it.
- Neither tool knows which changes were announced ahead or kept behind a version header. Stripe pins API versions per account.
