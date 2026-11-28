# Frontend testing handoff guides

**Planning documents only.** This branch implements white-box tests, not the assignments below.
Suggested tools and cases in these documents are not installed, configured, executed, or marked complete
by the white-box assignment.

| Separate assignment | Owner's guide | Main question |
|---|---|---|
| GUI testing | [GUI_TESTING.md](GUI_TESTING.md) | Are screens, controls, visual states, and navigation usable and correct? |
| Non-functional testing | [NON_FUNCTIONAL_TESTING.md](NON_FUNCTIONAL_TESTING.md) | Does the app meet agreed quality constraints? |
| Mutation testing | [MUTATION_TESTING.md](MUTATION_TESTING.md) | Do tests detect deliberate changes to application logic? |
| System testing — black box | [SYSTEM_BLACK_BOX_TESTING.md](SYSTEM_BLACK_BOX_TESTING.md) | Does the integrated system meet externally observable requirements? |
| Acceptance-level testing | [ACCEPTANCE_TESTING.md](ACCEPTANCE_TESTING.md) | Can intended users accomplish and approve the product's promised tasks? |

## Ownership boundaries

- White-box implementation and commands: `../../tests/README.md`.
- Other owners should create their own branches, test infrastructure, commits, case records, and reports.
- Do not count the white-box suite as GUI, non-functional, mutation, system, or acceptance evidence.
- A browser test with mocked APIs can demonstrate frontend behavior, but not a complete system journey.
- Acceptance is a stakeholder decision, not merely an automated test result.
- Coordinate overlapping scenarios using case IDs rather than claiming the same execution twice.
- Keep backend changes separate. Provision a disposable test backend when needed; never use production
  credentials/data or run destructive test fixtures against a production database.
- PDF reports are historical documents; this handoff does not edit or regenerate them.

## Shared case record

For each future case record: ID, requirement, priority, owner, environment and application revision,
preconditions, test data, numbered actions, expected result, actual result, pass/fail/blocked,
evidence location, defect reference, and cleanup.

Use `Not run` until an owner actually executes a case. Missing infrastructure is `Blocked`, not `Passed`.
Remove personal data, tokens, private source, and sensitive URLs from screenshots, traces, and reports.

## Suggested sequence

1. Agree ownership, requirements, and environments.
2. GUI owner establishes controlled screen/interaction checks.
3. System owner runs integrated black-box scenarios in an isolated stack.
4. Non-functional owner measures agreed constraints on a representative deployment.
5. Mutation owner assesses test sensitivity on scoped source files.
6. Acceptance owner schedules stakeholder evaluation against agreed criteria.

This sequence is coordination guidance, not an implemented pipeline.
