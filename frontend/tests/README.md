# Frontend white-box testing

This suite belongs only to the **white-box assignment**. It examines implementation decisions in
JavaScript functions. It does not render components, interact with a GUI, start a server, run system
or acceptance scenarios, measure non-functional qualities, or mutate production code.

## Setup and execution

Use Node 22. From `frontend/`, install the locked dependencies with `npm ci`.

| Command | Purpose |
|---|---|
| `npm test` | Run all white-box unit tests once |
| `npm run test:watch` | Rerun white-box tests during development |
| `npm run test:coverage` | Run instrumented tests and enforce scope-specific minimums |
| `npm test -- tests/services/api.paths.test.js` | Run one test file |
| `npm test -- -t "nested-data"` | Run matching test names |
| `npm run lint` | Static code check, not a test category |
| `npm run build` | Production compilation check, not a system/acceptance test |

Dependencies added for this assignment: Vitest and its V8 coverage provider.
The Node environment supplies `Event`, `EventTarget`, `Headers`, and text encoders/decoders.
Each API test substitutes `fetch`; tests never intentionally contact a backend.
`window` is a small event/redirect stub where required, not a rendered browser environment.

## Centralized layout

```text
tests/
├── graph/
│   └── graphAdapter.test.js
├── services/
│   ├── adapters.test.js
│   ├── api.test.js
│   └── api.paths.test.js
├── utils/
│   └── github.test.js
├── setup.js
└── README.md
```

All test files import the implementation from `src/`. The shared setup restores spies, substituted
globals, and timers after each test. There are no rendered-component/page tests or browser-test directories.

## White-box design and traceability

Cases are selected by reading the implementation, not solely from external user requirements.

| Source module | Internal decisions exercised | Test evidence |
|---|---|---|
| `src/utils/github.js` | Regex acceptance/rejection, null/empty guards, URL normalization, compound branch-name guards | `utils/github.test.js` |
| `src/services/adapters.js` | Status switches; optional-field fallbacks; error-message categorization; file-tree creation/sorting; importance/complexity boundaries; task/user mappings | `services/adapters.test.js` |
| `src/services/api.js` | Request success/204/error branches; nested validation details; status fallbacks; exception causes; auth-event conditions; ID/path encoding; token/hint normalization | `services/api.test.js`, `services/api.paths.test.js` |
| `src/services/api.js` | Source fallback/filter/sort/join paths; missing response fields; explanation-refresh conditions; conversation/task/history wrapper defaults; SSE parsing and error exits | `services/api.test.js`, `services/api.paths.test.js` |
| `src/components/graph/graphAdapter.js` | Node-type conditions/layer switches; nested payload selection; missing endpoint creation; adjacency/degree loops; root fallback; cycle termination; diamond/shared-dependency traversal | `graph/graphAdapter.test.js` |
| `src/components/graph/graphLayout.js` | Empty-input early return; orientation branches; coordinate transformation; nonmutation of input | `graph/graphAdapter.test.js` |

Graph tests examine plain arrays, maps, sets, and numerical positions. They do not render React Flow,
click graph controls, or verify visual layout. API wrapper tests inspect stub arguments and source-derived
branches; they do not prove server contracts, OAuth behavior, repository isolation, or integrated workflows.

## Coverage and limits

`vitest.config.js` names the five modules above explicitly, including them even if untested.
Coverage minimums are 95% statements, 85% branches, 95% functions, and 95% lines.
The HTML report is `coverage/index.html`; machine-readable totals are in `coverage/coverage-summary.json`.

Report measurements as **coverage of the white-box module scope**, never whole-frontend coverage.
Branch coverage does not prove all feasible paths, MC/DC, system correctness, UI usability, security,
performance, or mutation resistance. Never remove meaningful cases just to improve a percentage.

Verified Node 22 baseline: **203 tests in five files**. Scoped coverage: 99.42% statements,
90.12% branches, 100% functions, and 99.79% lines. These figures are measurements of the five
listed logic modules only, not evidence for any other testing assignment.

### Known uncovered source issue

`normalizeGraphData` has a bare-array input branch that assigns `rawNodes` but leaves `rawEdges`
and `rawStats` undefined. Later edge iteration therefore throws rather than returning a model.
That branch is not claimed as covered/supported by this suite. A production-code decision/fix and
a dedicated regression case are follow-up work; this assignment does not change application source.

Other coverage gaps are visible in the HTML report. Tests cover selected structural paths, not every
combination of optional fields or every malformed external payload.

## Other testing assignments

Only guidance is provided for teammates in `../docs/testing/`. Their implementation, execution,
test data, and results belong to their own branches/reports. No completion claims are made here.
