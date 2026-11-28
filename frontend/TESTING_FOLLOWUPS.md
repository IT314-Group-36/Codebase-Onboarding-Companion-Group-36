# Frontend testing ownership and follow-ups

## Implemented scope: white-box testing only

The executable suite is centralized in `tests/services/`, `tests/utils/`, and `tests/graph/`.
It uses Node-based Vitest, controlled dependency stubs, and V8 structural coverage.
See [tests/README.md](tests/README.md) for the scope matrix, commands, limits, and known source issue.

This assignment does not implement GUI, non-functional, mutation, system/black-box, or acceptance testing.
Application source, backend files, and PDF reports are not modified.

## White-box follow-ups

- Review uncovered branches in the five-module coverage report.
- Resolve the bare-array graph-normalization source issue before claiming that path works.
- Extend structural cases when implementation conditions, defaults, or loops change.
- Keep fresh mocks and globals per test; never replace a meaningful assertion with an empty catch.
- Do not claim full path coverage or MC/DC from a line/branch coverage percentage.

## Guidance-only handoff

Each assignment has its own document. None represents implemented tests or recorded execution results.

| Assignment | Guidance |
|---|---|
| GUI testing | [GUI_TESTING.md](docs/testing/GUI_TESTING.md) |
| Non-functional testing | [NON_FUNCTIONAL_TESTING.md](docs/testing/NON_FUNCTIONAL_TESTING.md) |
| Mutation testing | [MUTATION_TESTING.md](docs/testing/MUTATION_TESTING.md) |
| System testing — black-box cases | [SYSTEM_BLACK_BOX_TESTING.md](docs/testing/SYSTEM_BLACK_BOX_TESTING.md) |
| Acceptance-level testing | [ACCEPTANCE_TESTING.md](docs/testing/ACCEPTANCE_TESTING.md) |

The guides describe environments, suggested tooling, prioritized cases, expected outcomes,
evidence to collect, and ownership boundaries so teammates can implement them independently.
