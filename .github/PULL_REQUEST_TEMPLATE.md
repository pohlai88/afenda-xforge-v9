## Why

<!-- What problem this solves, or what the owner asked for. Link the spec or plan if there is one. -->

## Before

<!-- Behaviour or state before this PR. -->

## After

<!-- Behaviour or state after this PR merges. -->

## Verification

<!-- Printed counts, never exit codes: `afenda-pr`'s `pr evidence` check
     requires at least one `Ran N tests` / `of N tests` line and one commit
     id in this section. -->

| Gate | Command | Printed result | SHA |
|---|---|---|---|
| Tools suite | `python -m unittest discover afenda/tools/tests` | `Ran 307 tests … OK (skipped=1)` | `5d6b77378` |

## For the owner

<!-- Decisions or corrections that need the owner's ruling. "None." if there are none. -->

## Not verified

<!-- What no run exercised: gates skipped, edge cases untested, anything left for review to catch. -->
