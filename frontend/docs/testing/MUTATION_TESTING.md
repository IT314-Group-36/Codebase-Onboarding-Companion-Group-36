# Mutation testing — implementation guide for its owner

**Guidance only. No mutation runner, configuration, generated mutants, score, or CI execution is included.**

## Purpose and boundary

Mutation testing deliberately changes source operations and checks whether tests detect those changes.
It assesses test sensitivity, not statement/branch coverage, GUI correctness, or stakeholder acceptance.
Even when it reuses the white-box suite, its setup, execution, interpretation, and report are a separate assignment.

## Suggested setup

1. Create a dedicated mutation-testing branch with a clean working tree.
2. Use the locked Node/Vitest versions from the project. Run `npm ci` and confirm `npm test` passes first.
3. Evaluate StrykerJS with a Vitest runner whose compatibility matches the installed Vitest version.
   Do not assume the newest runner supports the current test framework; check its compatibility requirements.
4. Install and configure mutation tooling in your branch, not in the white-box-only setup.
5. Start with a small explicit source allowlist and the existing centralized tests.
6. Mutate application JavaScript, not tests, docs, coverage files, dependencies, generated output, or assets.
7. Run an initial dry run. Resolve sandbox/import/global-stub problems before interpreting scores.
8. Use tool-managed temporary copies/sandboxes; verify original application files remain unchanged afterwards.
9. Generate local HTML/machine-readable reports. Add a bounded CI job only after runtime/cost is understood.

## Initial source targets

| Target | Useful mutation operators/examples | Tests that should be sensitive |
|---|---|---|
| `src/utils/github.js` | Remove URL anchor, negate empty guard, change `&&` to `||`, remove traversal/trailing-slash guards | Accepted/rejected URL and branch partitions, boundary inputs |
| `src/services/adapters.js` | Change status cases, numeric thresholds, fallback values, sorting decisions, mapping fields | Error categorization, missing-field cases, tree sort, complexity/importance boundaries |
| `src/services/api.js` | Negate success/auth conditions, change 204 branch, drop supported hint/token fields, remove exception handling | Stubbed request/error/default/allowlist and SSE cases |
| `src/components/graph/graphAdapter.js` | Remove visited-set checks, change root condition, alter endpoint insertion, hide shared descendants | Cycle, missing-node, root-selection, diamond/shared-dependency cases |
| `src/components/graph/graphLayout.js` | Change empty guard, orientation/default values, coordinate offsets | Empty/layout-orientation/nonmutation cases |

Some geometry mutants may survive tests that assert only relative ordering. Investigate before changing
assertions: test a meaningful numerical invariant, not an arbitrary implementation constant solely for score.

## Suggested case records

| ID | Activity | Expected evidence |
|---|---|---|
| MUT-01 | Baseline unmodified code/test execution | Passing tests and exact revision/tool versions |
| MUT-02 | Mutate URL/branch guards | Mutant IDs killed by relevant invalid/valid input cases |
| MUT-03 | Mutate adapter thresholds and defaults | Kills attributable to boundary and fallback assertions |
| MUT-04 | Mutate API branching/field selection | Kills from error/success/allowlist tests without network dependency |
| MUT-05 | Mutate graph traversal/visited behavior | Kills or bounded timeouts with cycle/shared-dependency evidence |
| MUT-06 | Review surviving mutants | Per-mutant classification and follow-up, not just an aggregate score |
| MUT-07 | Repeat a selected run | Reproducibility and runtime data |

## Interpret results honestly

- **Killed:** a test detects the changed behavior.
- **Survived:** executed tests did not detect it; investigate missing assertions or equivalent behavior.
- **No coverage:** relevant mutated code was not exercised.
- **Timeout:** inspect for a genuine nonterminating path versus infrastructure slowness.
- **Compile/runtime/tool error:** report separately; it is not automatically evidence of a strong assertion.
- **Equivalent mutant:** document why observable behavior is unchanged; do not silently exclude inconvenient mutants.

Record the tool's score definition and denominator. Agree the required threshold with the team rather
than presenting a proposed value as an approved requirement. Do not compare scores from different mutation
scopes as if they were equivalent. White-box line/branch coverage is not a mutation score.

## Deliverables

Source allowlist, versioned configuration, baseline result, operator/scope settings, bounded execution
details, reports, survivor analysis, and proposed assertion improvements. Keep mutation artifacts and
execution ownership separate from the white-box assignment.
